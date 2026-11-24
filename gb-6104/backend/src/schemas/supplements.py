from datetime import date

from pydantic import BaseModel, Field

from src.constants.supplement_state import SupplementState


class SupplementInput(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    zone: str = Field(min_length=1, max_length=30)
    valid_from: str
    valid_until: str | None = None
    rate: int
    minimum: int
    note: str = Field(default="", max_length=500)
    recorded_from: str | None = None


class SupplementEntry(BaseModel):
    id: int
    code: str
    zone: str
    valid_from: date
    valid_until: date | None
    recorded_from: date
    recorded_until: date | None
    rate_cents: int
    min_cents: int
    note: str
    status: SupplementState
    failure: str | None
    digest: str
    attempts: int
    created_at: int
    created_by: str
