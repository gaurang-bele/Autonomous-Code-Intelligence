from pydantic import BaseModel

class ReviewDecision(BaseModel):
    approved: bool
    feedback: str | None = None
