"""Small validation schemas used at the web boundary."""

from pydantic import BaseModel, ConfigDict, Field


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    score: float | None
    error_message: str | None


class HealthRead(BaseModel):
    status: str = Field(default="ok")
