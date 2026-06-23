from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class VisaReconFilter(BaseModel):
    """Filter for the Visa / Card Reconciliation Monitor (Area 2).

    ``company_id`` scopes the WHOLE response — its summary KPIs, ``by_branch`` and
    ``daily_detail`` all reflect that company's own Visa journals, holding accounts
    and confirmation workflow. When ``None``, the service defaults to company 3
    (``#بالميه#.``, the only company with an active Geidea Visa-confirmation
    workflow) and flags ``is_default_company`` in the response; a company with no
    Visa workflow (e.g. company 2) returns empty/zeroed blocks gracefully.

    ``date_from``/``date_to`` drive ONLY the ``daily_detail`` block. The
    running-balance picture (``summary`` + ``by_branch`` + ``legacy_awareness``)
    is always full-history "as of today" and ignores the dates — a holding
    balance can be months old, so a date window would hide it (same reasoning as
    the POS monitor's live ``open_sessions`` block). Dates are optional; when
    absent the service defaults the daily window to the last 30 days.

    ``posted_only`` is accepted for shared-frontend-filter-shape parity (so the
    common filter payload validates without a 422); the service always reads only
    posted lines.
    """

    date_from: Optional[date] = Field(None, description="daily_detail window start (inclusive)")
    date_to: Optional[date] = Field(None, description="daily_detail window end (inclusive)")
    company_id: Optional[int] = Field(None, description="Company to scope the whole report (None = default company 3)")
    posted_only: bool = Field(True, description="Unused; accepted for filter-shape parity")
