"""General Ledger — paginated transaction history with running balance for one account."""
from __future__ import annotations

from api.models.common import GLFilter
from api.services.report_base import aggregate_lines_by_account


def compute_general_ledger(client, gl_filter: GLFilter) -> dict:
    account_id = gl_filter.account_id
    state_filter = [("parent_state", "=", "posted")] if gl_filter.posted_only else []

    # 1. Account info
    accounts = client.search_read(
        "account.account",
        domain=[("id", "=", account_id)],
        fields=["id", "code", "name", "account_type"],
        limit=1,
    )
    if not accounts:
        return {"error": "Account not found", "account_id": account_id}

    account = accounts[0]

    # 2. Opening balance: everything before date_from
    opening_domain: list = [
        ("account_id", "=", account_id),
        ("date", "<", gl_filter.date_from.isoformat()),
    ] + state_filter
    if gl_filter.company_id:
        opening_domain.append(("company_id", "=", gl_filter.company_id))

    opening_agg = aggregate_lines_by_account(client, opening_domain)
    opening_balance = round(opening_agg.get(account_id, {}).get("balance", 0.0), 2)

    # 3. Period transactions — server-side count then paginated fetch
    period_domain: list = [
        ("account_id", "=", account_id),
        ("date", ">=", gl_filter.date_from.isoformat()),
        ("date", "<=", gl_filter.date_to.isoformat()),
    ] + state_filter
    if gl_filter.company_id:
        period_domain.append(("company_id", "=", gl_filter.company_id))

    total_count = client.search_count("account.move.line", period_domain)

    lines = client.search_read(
        "account.move.line",
        domain=period_domain,
        fields=["id", "date", "move_id", "name", "ref",
                "partner_id", "debit", "credit"],
        order="date asc, id asc",
        offset=gl_filter.offset,
        limit=gl_filter.limit,
    )

    # 4. Running balance
    running = opening_balance
    formatted = []
    for line in lines:
        debit = round(line.get("debit", 0) or 0.0, 2)
        credit = round(line.get("credit", 0) or 0.0, 2)
        running = round(running + debit - credit, 2)

        move_field = line.get("move_id")
        partner_field = line.get("partner_id")

        formatted.append({
            "id": line["id"],
            "date": line.get("date", ""),
            "move_name": move_field[1] if isinstance(move_field, (list, tuple)) else "",
            "label": line.get("name") or "",
            "ref": line.get("ref") or "",
            "partner": partner_field[1] if isinstance(partner_field, (list, tuple)) else "",
            "debit": debit,
            "credit": credit,
            "running_balance": running,
        })

    closing_balance = running

    return {
        "account": account,
        "period": {
            "from": gl_filter.date_from.isoformat(),
            "to": gl_filter.date_to.isoformat(),
        },
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "total_lines": total_count,
        "lines": formatted,
        "pagination": {
            "offset": gl_filter.offset,
            "limit": gl_filter.limit,
            "has_more": (gl_filter.offset + gl_filter.limit) < total_count,
        },
    }
