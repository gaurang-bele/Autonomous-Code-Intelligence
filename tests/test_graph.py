import sqlite3
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from app.graph import build_graph

class Config:
    github_token = ""
    github_api_url = "https://api.github.com"

@pytest.fixture
def graph(monkeypatch):
    async def fetch(self, url):
        return {"pr_url": url, "repository": "owner/repo", "pr_number": 1, "branch_name": "feature",
                "code_contents": {"x.py": "def f(a,b): return a+b\n"},
                "file_metadata": {"x.py": {"sha": "old"}}}
    monkeypatch.setattr("app.graph.GitHubClient.fetch_pull_request", fetch)
    monkeypatch.setattr("app.graph.analyze_python_code", lambda code: "flake8: FAIL")
    monkeypatch.setattr("app.graph.generate_refactor", lambda name, code, lint, feedback="": code.replace("a,b", "a, b"))
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn); saver.setup()
    return build_graph(saver, Config())

@pytest.mark.asyncio
async def test_rejection_loops_to_refactor(graph):
    cfg = {"configurable": {"thread_id": "reject"}}
    first = await graph.ainvoke({"pr_url": "https://github.com/owner/repo/pull/1"}, cfg)
    assert first["status"] == "awaiting_review"
    graph.update_state(cfg, {"is_approved": False, "reviewer_feedback": "Use list comprehensions"})
    second = await graph.ainvoke(None, cfg)
    assert second["status"] == "awaiting_review"
    assert second["reviewer_feedback"] == "Use list comprehensions"
    assert sum(x["event"] == "propose_refactor" for x in second["history"]) == 2

@pytest.mark.asyncio
async def test_approval_commits_and_completes(graph, monkeypatch):
    async def commit(self, *args, **kwargs):
        return "https://github.com/owner/repo/commit/abc"
    monkeypatch.setattr("app.graph.GitHubClient.commit_files", commit)
    cfg = {"configurable": {"thread_id": "approve"}}
    await graph.ainvoke({"pr_url": "https://github.com/owner/repo/pull/1"}, cfg)
    graph.update_state(cfg, {"is_approved": True})
    result = await graph.ainvoke(None, cfg)
    assert result["status"] == "completed"
    assert result["commit_url"].endswith("/abc")
