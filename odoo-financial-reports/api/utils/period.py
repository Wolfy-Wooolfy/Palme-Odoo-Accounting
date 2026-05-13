from __future__ import annotations

from datetime import date


def period_display(date_from: date, date_to: date) -> str:
    return f"{date_from.isoformat()} → {date_to.isoformat()}"


def build_move_domain(
    date_from: date | None,
    date_to: date,
    company_id: int | None,
    posted_only: bool,
    cumulative: bool = False,
) -> list:
    """Build an account.move.line domain.

    If cumulative=True, omits date_from (balance-sheet style: all entries up to date_to).
    """
    domain: list = [("date", "<=", date_to.isoformat())]
    if not cumulative and date_from is not None:
        domain.append(("date", ">=", date_from.isoformat()))
    if posted_only:
        domain.append(("parent_state", "=", "posted"))
    if company_id is not None:
        domain.append(("company_id", "=", company_id))
    return domain
