"""Cash & Bank report — balance and period movements for all bank/cash journals."""
from __future__ import annotations

from api.models.common import ReportFilter
from api.services.report_base import aggregate_lines_by_account


def compute_cash_bank(client, filters: ReportFilter) -> dict:
    # 1. Get all bank/cash journals
    journal_domain: list = [("type", "in", ["bank", "cash"])]
    if filters.company_id:
        journal_domain.append(("company_id", "=", filters.company_id))

    journals = client.search_read(
        "account.journal",
        domain=journal_domain,
        fields=["id", "name", "type", "code", "default_account_id", "company_id"],
        limit=200,
    )

    if not journals:
        return _empty_response(filters)

    # 2. Map account_id → journal
    account_to_journal: dict[int, dict] = {}
    for j in journals:
        acc_field = j.get("default_account_id")
        if acc_field and isinstance(acc_field, (list, tuple)) and acc_field[0]:
            account_to_journal[acc_field[0]] = j

    if not account_to_journal:
        return _empty_response(filters)

    account_ids = list(account_to_journal.keys())
    state_filter = [("parent_state", "=", "posted")] if filters.posted_only else []

    # 3. Cumulative balance (all time up to date_to)
    cum_domain: list = [
        ("account_id", "in", account_ids),
        ("date", "<=", filters.date_to.isoformat()),
    ] + state_filter
    if filters.company_id:
        cum_domain.append(("company_id", "=", filters.company_id))
    cum_balances = aggregate_lines_by_account(client, cum_domain)

    # 4. Period movements (date_from to date_to)
    per_domain: list = [
        ("account_id", "in", account_ids),
        ("date", ">=", filters.date_from.isoformat()),
        ("date", "<=", filters.date_to.isoformat()),
    ] + state_filter
    if filters.company_id:
        per_domain.append(("company_id", "=", filters.company_id))
    per_balances = aggregate_lines_by_account(client, per_domain)

    # 5. Build result rows
    result_journals = []
    for acc_id, j in account_to_journal.items():
        cum = cum_balances.get(acc_id, {})
        per = per_balances.get(acc_id, {})
        company_name = ""
        if j.get("company_id") and isinstance(j["company_id"], (list, tuple)):
            company_name = j["company_id"][1]

        result_journals.append({
            "journal_id": j["id"],
            "journal_name": j["name"],
            "journal_type": j["type"],
            "journal_code": j.get("code", ""),
            "company": company_name,
            "ending_balance": round(cum.get("balance", 0), 2),
            "period_inflow": round(per.get("debit", 0), 2),
            "period_outflow": round(per.get("credit", 0), 2),
            "period_net": round(per.get("balance", 0), 2),
        })

    # Banks first, then cash; within each group sort by ending_balance desc
    result_journals.sort(key=lambda x: (x["journal_type"] != "bank", -x["ending_balance"]))

    totals = {
        "ending_balance": round(sum(j["ending_balance"] for j in result_journals), 2),
        "period_inflow": round(sum(j["period_inflow"] for j in result_journals), 2),
        "period_outflow": round(sum(j["period_outflow"] for j in result_journals), 2),
        "period_net": round(sum(j["period_net"] for j in result_journals), 2),
        "bank_count": sum(1 for j in result_journals if j["journal_type"] == "bank"),
        "cash_count": sum(1 for j in result_journals if j["journal_type"] == "cash"),
    }

    return {
        "period": {
            "from": filters.date_from.isoformat(),
            "to": filters.date_to.isoformat(),
        },
        "journals": result_journals,
        "totals": totals,
    }


def _empty_response(filters: ReportFilter) -> dict:
    return {
        "period": {
            "from": filters.date_from.isoformat(),
            "to": filters.date_to.isoformat(),
        },
        "journals": [],
        "totals": {
            "ending_balance": 0.0,
            "period_inflow": 0.0,
            "period_outflow": 0.0,
            "period_net": 0.0,
            "bank_count": 0,
            "cash_count": 0,
        },
    }
