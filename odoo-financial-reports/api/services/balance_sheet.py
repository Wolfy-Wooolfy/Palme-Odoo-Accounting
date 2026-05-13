from __future__ import annotations

from api.models.common import ReportFilter
from api.services.report_base import aggregate_lines_by_account, get_accounts
from api.utils.period import build_move_domain

ASSET_TYPES = frozenset({
    "asset_receivable", "asset_cash", "asset_current",
    "asset_non_current", "asset_prepayments", "asset_fixed",
})
LIABILITY_TYPES = frozenset({
    "liability_payable", "liability_credit_card",
    "liability_current", "liability_non_current",
})
EQUITY_TYPES = frozenset({"equity", "equity_unaffected"})
PL_TYPES = frozenset({
    "income", "income_other",
    "expense", "expense_depreciation", "expense_direct_cost",
})
BS_TYPES = list(ASSET_TYPES | LIABILITY_TYPES | EQUITY_TYPES)


def compute_balance_sheet(client, filters: ReportFilter) -> dict:
    accounts = get_accounts(client, account_types=BS_TYPES, company_id=filters.company_id)
    if not accounts:
        return _empty_response(filters)

    account_ids = [a["id"] for a in accounts]
    domain = build_move_domain(
        date_from=None,
        date_to=filters.date_to,
        company_id=filters.company_id,
        posted_only=filters.posted_only,
        cumulative=True,
    )
    domain.append(("account_id", "in", account_ids))

    by_account = aggregate_lines_by_account(client, domain)

    asset_accounts = []
    liability_accounts = []
    equity_accounts = []

    for acc in accounts:
        agg = by_account.get(acc["id"], {})
        balance = agg.get("balance", 0.0)
        if balance == 0.0:
            continue
        row = {
            "account_id": acc["id"],
            "code": acc["code"] or "",
            "name": acc["name"],
            "account_type": acc["account_type"],
            "balance": round(balance, 2),
        }
        if acc["account_type"] in ASSET_TYPES:
            asset_accounts.append(row)
        elif acc["account_type"] in LIABILITY_TYPES:
            liability_accounts.append(row)
        elif acc["account_type"] in EQUITY_TYPES:
            equity_accounts.append(row)

    for section in (asset_accounts, liability_accounts, equity_accounts):
        section.sort(key=lambda x: x["code"])

    # ── Synthetic "Current Period Earnings" ──────────────────────────────────
    # Cumulative P&L is NOT included in BS accounts. In Odoo 17 Enterprise, the
    # Year Closing wizard closes P&L to retained earnings (equity_unaffected).
    # If that hasn't been run, we compute the synthetic retained earnings here.
    pl_accounts = get_accounts(
        client,
        account_types=list(PL_TYPES),
        company_id=filters.company_id,
    )
    if pl_accounts:
        pl_ids = [a["id"] for a in pl_accounts]
        pl_domain = build_move_domain(
            date_from=None,
            date_to=filters.date_to,
            company_id=filters.company_id,
            posted_only=filters.posted_only,
            cumulative=True,
        )
        pl_domain.append(("account_id", "in", pl_ids))

        pl_by_acc = aggregate_lines_by_account(client, pl_domain)
        cumulative_pl_balance = sum(d.get("balance", 0.0) for d in pl_by_acc.values())

        if abs(cumulative_pl_balance) >= 1:
            # In the debit-credit model:
            # - Revenue accounts have NEGATIVE balance (credit > debit)
            # - Expense accounts have POSITIVE balance (debit > credit)
            # - cumulative_pl_balance = expenses_balance - revenue_balance_magnitude
            # - For a profitable company: cumulative_pl_balance < 0
            # - Synthetic equity balance = cumulative_pl_balance (also negative → credit entry)
            #   This makes assets + liab + equity + pl_balance = 0 → BS balances
            equity_accounts.append({
                "account_id": -1,
                "code": "ZZZ-RE",
                "name": "Current Period Earnings (Synthetic)",
                "account_type": "equity_unaffected",
                "balance": round(cumulative_pl_balance, 2),
                "is_synthetic": True,
            })

    total_assets = round(sum(r["balance"] for r in asset_accounts), 2)
    total_liabilities = round(sum(r["balance"] for r in liability_accounts), 2)
    total_equity = round(sum(r["balance"] for r in equity_accounts), 2)
    balance_check = round(total_assets + total_liabilities + total_equity, 2)

    return {
        "as_of": filters.date_to.isoformat(),
        "assets": {"accounts": asset_accounts, "total": total_assets},
        "liabilities": {"accounts": liability_accounts, "total": total_liabilities},
        "equity": {"accounts": equity_accounts, "total": total_equity},
        "total_liabilities_and_equity": round(total_liabilities + total_equity, 2),
        "balance_check": balance_check,
    }


def _empty_response(filters: ReportFilter) -> dict:
    return {
        "as_of": filters.date_to.isoformat(),
        "assets": {"accounts": [], "total": 0.0},
        "liabilities": {"accounts": [], "total": 0.0},
        "equity": {"accounts": [], "total": 0.0},
        "total_liabilities_and_equity": 0.0,
        "balance_check": 0.0,
    }
