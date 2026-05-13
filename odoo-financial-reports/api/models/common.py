from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PeriodFilter(BaseModel):
    date_from: date = Field(..., description="Start date (inclusive)")
    date_to: date = Field(..., description="End date (inclusive)")

    @model_validator(mode="after")
    def date_to_must_be_gte_date_from(self) -> "PeriodFilter":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be >= date_from")
        return self


class ReportFilter(PeriodFilter):
    company_id: Optional[int] = Field(None, description="Filter by company ID (None = all companies)")
    posted_only: bool = Field(True, description="Include only posted journal entries")
