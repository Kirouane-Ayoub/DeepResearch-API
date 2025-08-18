from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    topic: str = Field(..., description="The research topic to investigate")
    max_review_cycles: Optional[int] = Field(
        3, description="Maximum number of review cycles"
    )
    timeout: Optional[int] = Field(300, description="Timeout in seconds")


class ResearchResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ResearchStatus(BaseModel):
    session_id: str
    status: str
    progress: Optional[str] = None
    result: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ResearchResult(BaseModel):
    session_id: str
    topic: str
    report: str
    completed_at: datetime
    review_cycles: int
