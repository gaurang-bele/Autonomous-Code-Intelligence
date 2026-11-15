from typing import Any, TypedDict

class ReviewState(TypedDict, total=False):
    pr_url: str
    repository: str
    pr_number: int
    branch_name: str
    code_contents: dict[str, str]
    file_metadata: dict[str, dict[str, Any]]
    lint_errors: dict[str, str]
    refactored_code: dict[str, str]
    is_approved: bool | None
    reviewer_feedback: str
    history: list[dict[str, Any]]
    commit_url: str
    status: str
