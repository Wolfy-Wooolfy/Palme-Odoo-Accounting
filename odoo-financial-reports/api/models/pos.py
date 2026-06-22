from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PosMonitorFilter(BaseModel):
    """Filter for the POS Session Monitor (Area 1).

    `date_from`/`date_to` apply to the *by_branch* block only; the
    *open_sessions* block is LIVE and ignores them (a session can be open for
    600+ days, i.e. it started long before any date_from). Dates are optional —
    when absent the service defaults to the last 90 days.

    `posted_only` is unused here (POS sessions are operational records, not
    journal entries) but is accepted so the shared frontend filter payload
    validates without a 422.
    """

    date_from: Optional[date] = Field(None, description="by_branch period start (inclusive)")
    date_to: Optional[date] = Field(None, description="by_branch period end (inclusive)")
    company_id: Optional[int] = Field(None, description="Filter by company ID (None = all companies)")
    posted_only: bool = Field(True, description="Unused; accepted for filter-shape parity")
