"""Shared helpers used by all financial report services."""
from __future__ import annotations

from datetime import date
from typing import Any

from api.models.common import ReportFilter
from api.utils.period import build_move_domain


def aggregate_lines_by_account(
    client,
    domain: list,
    limit: int = 5000,
) -> dict[int, dict[str, float]]:
    """
    Run read_group on account.move.line, returning a mapping of
    account_id -> {debit, credit, balance}.

    Uses server-side aggregation (read_group) — never fetches individual rows.
    Critical for performance with 4M+ journal items.
    """
    grouped = client.execute_kw(
        "account.move.line",
        "read_group",
        [domain, ["debit:sum", "credit:sum"], ["account_id"]],
        {"lazy": False, "limit": limit},
    )
    result: dict[int, dict[str, float]] = {}
    for g in grouped:
        acc_field = g.get("account_id")
        if not acc_field:
            continue
        acc_id = acc_field[0] if isinstance(acc_field, (list, tuple)) else acc_field
        debit = g.get("debit") or 0.0
        credit = g.get("credit") or 0.0
        result[acc_id] = {
            "debit": debit,
            "credit": credit,
            "balance": debit - credit,
        }
    return result


def get_accounts(
    client,
    account_types: list[str] | None = None,
    company_id: int | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Fetch chart of accounts, optionally filtered by account_type."""
    domain: list = [("deprecated", "=", False)]
    if account_types:
        domain.append(("account_type", "in", account_types))
    if company_id is not None:
        domain.append(("company_id", "=", company_id))
    return client.search_read(
        "account.account",
        domain=domain,
        fields=["id", "code", "name", "account_type"],
        limit=limit,
    )
