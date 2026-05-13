from __future__ import annotations

from api.models.common import ReportFilter
from api.services.report_base import aggregate_lines_by_account, get_accounts
from api.utils.period import build_move_domain


def compute_trial_balance(client, filters: ReportFilter) -> list[dict]:
    accounts = get_accounts(client, company_id=filters.company_id)

    domain = build_move_domain(
        filters.date_from,
        filters.date_to,
        filters.company_id,
        filters.posted_only,
        cumulative=False,
    )

    by_account = aggregate_lines_by_account(client, domain)

    rows = []
    for acc in accounts:
        agg = by_account.get(acc["id"], {})
        debit = agg.get("debit", 0.0)
        credit = agg.get("credit", 0.0)
        balance = agg.get("balance", 0.0)
        if not (debit or credit or balance):
            continue
        rows.append(
            {
                "account_id": acc["id"],
                "code": acc["code"] or "",
                "name": acc["name"],
                "account_type": acc["account_type"],
                "debit": round(debit, 2),
                "credit": round(credit, 2),
                "balance": round(balance, 2),
            }
        )

    rows.sort(key=lambda r: r["code"])
    return rows
