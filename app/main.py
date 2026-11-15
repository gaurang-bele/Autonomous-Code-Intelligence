import hashlib, hmac, json, logging, sqlite3, uuid
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import RedirectResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import get_settings
from app.graph import build_graph
from app.schemas import ReviewDecision

settings = get_settings()
Path(settings.checkpoint_db).parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
saver = SqliteSaver(db)
saver.setup()
graph = build_graph(saver, settings)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("code-review-agent")
app = FastAPI(title="Autonomous Code Review & Refactoring Agent", version="1.0.0")

def config(thread_id):
    return {"configurable": {"thread_id": thread_id}}

def verify_signature(body, signature):
    if not settings.github_webhook_secret:
        return
    expected = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid GitHub webhook signature")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/webhooks/github", status_code=202)
async def github_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    if payload.get("action", "opened") not in {"opened", "reopened", "synchronize", "ready_for_review"}:
        return {"status": "ignored"}
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    url = pr.get("html_url") or payload.get("pr_url")
    if not url and repo.get("full_name") and pr.get("number"):
        url = f"https://github.com/{repo['full_name']}/pull/{pr['number']}"
    if not url:
        raise HTTPException(422, "Expected pull_request.html_url or repository.full_name + pull_request.number")
    thread_id = str(uuid.uuid4())
    try:
        result = await graph.ainvoke({"pr_url": str(url), "is_approved": None,
                                      "reviewer_feedback": "", "history": [], "status": "started"},
                                     config(thread_id))
    except Exception as exc:
        logger.exception("PR pipeline failed")
        raise HTTPException(502, f"PR pipeline failed: {exc}") from exc
    return {"thread_id": thread_id, "status": result.get("status"),
            "files_fetched": len(result.get("code_contents", {})),
            "lint_errors": result.get("lint_errors", {}),
            "refactored_code": result.get("refactored_code", {}), "approval_required": True}

@app.post("/api/reviews/{thread_id}/approve")
async def submit_review(thread_id: str, decision: ReviewDecision):
    cfg = config(thread_id)
    snapshot = graph.get_state(cfg)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Review thread not found")
    if snapshot.values.get("status") == "completed":
        raise HTTPException(409, "Review already completed")
    if not decision.approved and not (decision.feedback or "").strip():
        raise HTTPException(422, "Feedback is required when rejecting")
    graph.update_state(cfg, {"is_approved": decision.approved,
                             "reviewer_feedback": (decision.feedback or "").strip()})
    try:
        result = await graph.ainvoke(None, cfg)
    except Exception as exc:
        logger.exception("Resume failed")
        raise HTTPException(502, f"Could not resume review: {exc}") from exc
    return {"thread_id": thread_id, "status": result.get("status"),
            "approval_required": result.get("status") != "completed",
            "commit_url": result.get("commit_url"),
            "refactored_code": result.get("refactored_code", {}),
            "history": result.get("history", [])}

@app.get("/api/reviews/{thread_id}")
async def get_review(thread_id: str):
    snap = graph.get_state(config(thread_id))
    if not snap or not snap.values:
        raise HTTPException(404, "Review thread not found")
    v = snap.values
    return {k: v.get(k) for k in ("status", "pr_url", "lint_errors", "refactored_code",
            "is_approved", "reviewer_feedback", "commit_url", "history")} | {"thread_id": thread_id}

@app.on_event("shutdown")
def close_db():
    db.close()
