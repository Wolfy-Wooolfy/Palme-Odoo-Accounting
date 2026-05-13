from __future__ import annotations

from api.models.common import ReportFilter
from api.services.report_base import aggregate_lines_by_account, get_accounts
from api.utils.period import build_move_domain

REVENUE_TYPES = frozenset({"income", "income_other"})
EXPENSE_TYPES = frozenset({"expense", "expense_depreciation", "expense_direct_cost"})
PL_TYPES = list(REVENUE_TYPES | EXPENSE_TYPES)


def compute_profit_loss(client, filters: ReportFilter) -> dict:
    accounts = get_accounts(client, account_types=PL_TYPES, company_id=filters.company_id)
    if not accounts:
        return _empty_response(filters)

    account_ids = [a["id"] for a in accounts]
    domain = build_move_domain(
        filters.date_from,
        filters.date_to,
        filters.company_id,
        filters.posted_only,
        cumulative=False,
    )
    domain.append(("account_id", "in", account_ids))

    by_account = aggregate_lines_by_account(client, domain)

    revenue_accounts = []
    expense_accounts = []

    for acc in accounts:
        agg = by_account.get(acc["id"], {})
        balance = agg.get("balance", 0.0)
        if balance == 0.0:
            continue
        row = {
            "account_id": acc["id"],
            "code": acc["code"] or "",
            "name": acc["name"],
            "balance": round(balance, 2),
            "amount": 0.0,
        }
        if acc["account_type"] in REVENUE_TYPES:
            row["amount"] = round(-balance, 2)  # revenue credit nature → negate
            revenue_accounts.append(row)
        elif acc["account_type"] in EXPENSE_TYPES:
            row["amount"] = round(balance, 2)
            expense_accounts.append(row)

    revenue_accounts.sort(key=lambda x: -x["amount"])
    expense_accounts.sort(key=lambda x: -x["amount"])

    total_revenue = round(sum(r["amount"] for r in revenue_accounts), 2)
    total_expenses = round(sum(r["amount"] for r in expense_accounts), 2)

    return {
        "period": {
            "from": filters.date_from.isoformat(),
            "to": filters.date_to.isoformat(),
        },
        "revenue": {"accounts": revenue_accounts, "total": total_revenue},
        "expenses": {"accounts": expense_accounts, "total": total_expenses},
        "net_profit": round(total_revenue - total_expenses, 2),
    }


def _empty_response(filters: ReportFilter) -> dict:
    return {
        "period": {"from": filters.date_from.isoformat(), "to": filters.date_to.isoformat()},
        "revenue": {"accounts": [], "total": 0.0},
        "expenses": {"accounts": [], "total": 0.0},
        "net_profit": 0.0,
    }
