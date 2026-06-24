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


class VisaBranchDetailFilter(BaseModel):
    """Filter for the Visa branch session-level drill-down (Area 2, Phase 3B+).

    Opens ONE branch journal of ONE company and lists the POS sessions that make up
    that branch's still-pending (collected-but-not-yet-confirmed) holding balance —
    so the accountant sees exactly which session-batches are unconfirmed. Confirmation
    is per branch-batch (a Geidea lump settles many sessions at once), so this is the
    SESSION level — NOT a per-individual-sale confirmation.

    ``company_id`` and ``journal_id`` are both REQUIRED (the branch is meaningless
    without its owning company). ``date_from``/``date_to`` are accepted only for
    shared-frontend-filter-shape parity and are IGNORED: like the main screen's
    running-balance view, the pending list is always full-history "as of today" (a
    holding balance can be months old, so a date window would hide it).
    """

    company_id: int = Field(..., description="Company that owns the branch journal (required)")
    journal_id: int = Field(..., description="The branch Visa journal to drill into (required)")
    date_from: Optional[date] = Field(None, description="Ignored; accepted for filter-shape parity")
    date_to: Optional[date] = Field(None, description="Ignored; accepted for filter-shape parity")
    posted_only: bool = Field(True, description="Unused; the service always reads only posted lines")
