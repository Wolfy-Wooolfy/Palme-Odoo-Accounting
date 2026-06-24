from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BankMovementsFilter(BaseModel):
    """Filter for the Bank Movements & Gaps screen (Area 3).

    Scope = the 27 REAL bank/treasury journals (Visa-holding journals are Area 2
    and excluded) + the bank-side ``account.payment`` universe + the bank-suspense
    accounts. Cash drawers (Area 1) and card holding balances (Area 2) are NOT part
    of this screen — no double-counting.

    ``company_id`` scopes the WHOLE response. ``None`` = all real-bank companies.

    Two distinct time semantics (each block states which it uses):
      * **GAP totals are full-history "as of today"** — a backlog gap can be months
        old (the oldest unreconciled payment is 2024-06-01), so a date window would
        hide it. The summary gap KPIs, the per-bank gap columns, the suspense block
        and (when ``gaps_only`` is true) the movements list all ignore the dates.
      * **MOVEMENT VOLUME is date-windowed** — ``date_from``/``date_to`` drive the
        movement-volume KPIs, the per-bank movement columns, and (when ``gaps_only``
        is false) the movements list. Default window = last 90 days.

    ``gaps_only`` (default true) flips the movements list between the unreconciled
    backlog (oldest-first, date-independent) and all posted movements in the window
    (newest-first). The summary is computed in FULL regardless of this flag.

    ``offset``/``limit`` paginate the movements list (``total_count`` is returned so
    the UI can show "showing N of M"). ``posted_only`` is accepted for shared
    filter-shape parity; the service always reads only posted records.
    """

    date_from: Optional[date] = Field(None, description="Movement-volume window start (inclusive); default = 90 days back")
    date_to: Optional[date] = Field(None, description="Movement-volume window end (inclusive); default = today")
    company_id: Optional[int] = Field(None, description="Company to scope the whole report (None = all real-bank companies)")
    gaps_only: bool = Field(True, description="Movements list: true = unreconciled backlog (date-independent); false = all posted movements in the window")
    offset: int = Field(0, ge=0, description="Movements-list pagination offset")
    limit: int = Field(200, ge=1, le=1000, description="Movements-list rows per page")
    posted_only: bool = Field(True, description="Unused; accepted for filter-shape parity (the service always reads only posted records)")


class BankGapDetailFilter(BaseModel):
    """Filter for the per-bank GAP drill-down (Area 3).

    Opens ONE bank journal and lists the unreconciled ``account.payment`` movements
    that make up that journal's GAP — so the user sees exactly which payments are the
    gap. The gap is full-history "as of today" (a backlog can be months old), so this
    drill-down — like the main screen's per-bank gap columns — IGNORES the date window
    entirely and always reads the full unreconciled backlog, oldest-first.

    ``journal_id`` is REQUIRED. ``company_id`` is the SAME optional whole-report scope
    as the main screen (``None`` = no company filter); since ``journal_id`` already pins
    one company, the header ``gap_count``/``gap_amount`` returned here tie EXACTLY to that
    journal's row on the main ``by_bank`` table for the same ``company_id`` scope.

    ``offset``/``limit`` paginate the movements list (``total_count`` is returned so the
    UI can show "showing N of M"). ``posted_only`` is accepted for shared filter-shape
    parity; the service always reads only posted records.
    """

    company_id: Optional[int] = Field(None, description="Same whole-report scope as the main screen (None = no company filter)")
    journal_id: int = Field(..., description="The bank journal to drill into (required)")
    offset: int = Field(0, ge=0, description="Movements-list pagination offset")
    limit: int = Field(50, ge=1, le=1000, description="Movements-list rows per page")
    posted_only: bool = Field(True, description="Unused; accepted for filter-shape parity (the service always reads only posted records)")
