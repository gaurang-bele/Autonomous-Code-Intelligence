from datetime import datetime, timezone
from typing import Literal
from langgraph.graph import StateGraph, START, END
from app.github_client import GitHubClient
from app.refactor import generate_refactor
from app.sandbox import analyze_python_code
from app.state import ReviewState

def history(state, event, **data):
    return (state.get("history") or []) + [{"event": event, "at": datetime.now(timezone.utc).isoformat(), **data}]

def build_graph(checkpointer, settings):
    async def fetch_pr_node(state: ReviewState):
        pr = await GitHubClient(settings.github_token, settings.github_api_url).fetch_pull_request(state["pr_url"])
        return {**pr, "status": "pr_fetched", "history": history(state, "fetch_pr", files=len(pr["code_contents"]))}

    def lint_code_node(state: ReviewState):
        reports = {name: analyze_python_code(code) for name, code in state.get("code_contents", {}).items() if name.endswith(".py")}
        if not reports:
            reports["_notice"] = "No Python files found."
        return {"lint_errors": reports, "status": "linted", "history": history(state, "lint_code", files=len(reports))}

    def propose_refactor_node(state: ReviewState):
        proposals = {}
        for name, code in state.get("code_contents", {}).items():
            if name.endswith(".py"):
                proposals[name] = generate_refactor(name, code, state.get("lint_errors", {}).get(name, ""),
                                                    state.get("reviewer_feedback", ""))
        if not proposals:
            raise ValueError("No Python files found to refactor")
        return {"refactored_code": proposals, "is_approved": None, "status": "awaiting_review",
                "history": history(state, "propose_refactor", files=len(proposals))}

    async def apply_changes_node(state: ReviewState):
        # On rejection this node performs no write; its outgoing edge returns to the refactor node.
        if state.get("is_approved") is not True:
            return {"status": "refactor_requested",
                    "history": history(state, "review_rejected", feedback=state.get("reviewer_feedback", ""))}
        url = await GitHubClient(settings.github_token, settings.github_api_url).commit_files(
            state["repository"], state["branch_name"], state["refactored_code"],
            state.get("file_metadata", {}), f"Apply AI refactor for PR #{state['pr_number']}")
        return {"commit_url": url, "status": "completed",
                "history": history(state, "changes_committed", commit_url=url)}

    def after_apply(state: ReviewState) -> Literal["refactor", "end"]:
        return "end" if state.get("is_approved") is True else "refactor"

    g = StateGraph(ReviewState)
    g.add_node("fetch_pr_node", fetch_pr_node)
    g.add_node("lint_code_node", lint_code_node)
    g.add_node("propose_refactor_node", propose_refactor_node)
    g.add_node("apply_changes_node", apply_changes_node)
    g.add_edge(START, "fetch_pr_node")
    g.add_edge("fetch_pr_node", "lint_code_node")
    g.add_edge("lint_code_node", "propose_refactor_node")
    g.add_edge("propose_refactor_node", "apply_changes_node")
    g.add_conditional_edges("apply_changes_node", after_apply, {"refactor": "propose_refactor_node", "end": END})
    return g.compile(checkpointer=checkpointer, interrupt_before=["apply_changes_node"])
