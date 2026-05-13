"""Balance Sheet diagnostic — investigates why Assets ≠ Liabilities + Equity."""
from __future__ import annotations

from datetime import date

from api.services.report_base import aggregate_lines_by_account, get_accounts

KNOWN_BS_TYPES: frozenset[str] = frozenset({
    "asset_receivable", "asset_cash", "asset_current",
    "asset_non_current", "asset_prepayments", "asset_fixed",
    "liability_payable", "liability_credit_card",
    "liability_current", "liability_non_current",
    "equity", "equity_unaffected",
})
KNOWN_PL_TYPES: frozenset[str] = frozenset({
    "income", "income_other",
    "expense", "expense_depreciation", "expense_direct_cost",
})
ALL_KNOWN: frozenset[str] = KNOWN_BS_TYPES | KNOWN_PL_TYPES


def diagnose_balance_sheet(client, as_of: date, company_id: int | None, posted_only: bool) -> dict:
    issues: list[dict] = []
    base_state_filter = [("parent_state", "=", "posted")] if posted_only else []

    # ── Check 1: Discover all account types ─────────────────────────────────
    acc_domain: list = [("deprecated", "=", False)]
    if company_id:
        acc_domain.append(("company_id", "=", company_id))

    all_accounts = client.search_read(
        "account.account",
        domain=acc_domain,
        fields=["id", "code", "name", "account_type"],
        limit=3000,
    )

    types_in_use = {a["account_type"] for a in all_accounts if a.get("account_type")}
    unknown_types = types_in_use - ALL_KNOWN

    if unknown_types:
        issues.append({
            "severity": "high",
            "type": "unknown_account_types",
            "message": f"Found {len(unknown_types)} account type(s) not categorized as BS or PL",
            "types": sorted(unknown_types),
        })

    # ── Check 2: Aggregate balances for unknown-type accounts ────────────────
    if unknown_types:
        unknown_accounts = [a for a in all_accounts if a.get("account_type") in unknown_types]
        unknown_ids = [a["id"] for a in unknown_accounts]

        unk_domain: list = [
            ("date", "<=", as_of.isoformat()),
            ("account_id", "in", unknown_ids),
        ] + base_state_filter
        if company_id:
            unk_domain.append(("company_id", "=", company_id))

        by_unk = aggregate_lines_by_account(client, unk_domain)
        unknown_details = [
            {
                "code": a["code"],
                "name": a["name"],
                "account_type": a["account_type"],
                "balance": round(by_unk.get(a["id"], {}).get("balance", 0), 2),
            }
            for a in unknown_accounts
            if by_unk.get(a["id"], {}).get("balance", 0) != 0
        ]
        if unknown_details:
            total_unk = round(sum(d["balance"] for d in unknown_details), 2)
            issues.append({
                "severity": "high",
                "type": "uncategorized_balances",
                "message": (
                    f"{len(unknown_details)} account(s) with uncategorized types "
                    f"have non-zero balances totalling {total_unk:,.2f}"
                ),
                "total_balance": total_unk,
                "accounts": sorted(unknown_details, key=lambda x: -abs(x["balance"]))[:20],
            })

    # ── Check 3 & 4: BS section totals ───────────────────────────────────────
    bs_accounts = [a for a in all_accounts if a.get("account_type") in KNOWN_BS_TYPES]
    bs_ids = [a["id"] for a in bs_accounts]

    bs_domain: list = [
        ("date", "<=", as_of.isoformat()),
        ("account_id", "in", bs_ids),
    ] + base_state_filter
    if company_id:
        bs_domain.append(("company_id", "=", company_id))

    bs_by_acc = aggregate_lines_by_account(client, bs_domain)

    assets_total = liab_total = equity_total = 0.0
    for acc in bs_accounts:
        bal = bs_by_acc.get(acc["id"], {}).get("balance", 0.0)
        t = acc["account_type"]
        if t.startswith("asset_"):
            assets_total += bal
        elif t.startswith("liability_"):
            liab_total += bal
        else:
            equity_total += bal

    expected_zero = round(assets_total + liab_total + equity_total, 2)

    issues.append({
        "severity": "info",
        "type": "balance_breakdown",
        "message": "Raw debit-credit balance totals for each BS section",
        "assets_total": round(assets_total, 2),
        "liabilities_total_raw": round(liab_total, 2),
        "equity_total_raw": round(equity_total, 2),
        "sum_all_sections": expected_zero,
        "note": (
            "sum_all_sections should be 0 for balanced books "
            "(debit-credit model: assets positive, liab/equity negative)"
        ),
    })

    # ── Check 5: Cumulative P&L ───────────────────────────────────────────────
    pl_accounts = [a for a in all_accounts if a.get("account_type") in KNOWN_PL_TYPES]
    pl_ids = [a["id"] for a in pl_accounts]

    pl_domain: list = [
        ("date", "<=", as_of.isoformat()),
        ("account_id", "in", pl_ids),
    ] + base_state_filter
    if company_id:
        pl_domain.append(("company_id", "=", company_id))

    pl_by_acc = aggregate_lines_by_account(client, pl_domain)
    cumulative_pl_balance = round(sum(d.get("balance", 0) for d in pl_by_acc.values()), 2)
    cumulative_net_profit = round(-cumulative_pl_balance, 2)

    issues.append({
        "severity": "info",
        "type": "cumulative_pl",
        "message": "Cumulative P&L balance — should equal missing equity if P&L isn't closed",
        "cumulative_pl_balance": cumulative_pl_balance,
        "cumulative_net_profit": cumulative_net_profit,
        "note": "If |sum_all_sections| ≈ cumulative_net_profit, the P&L has not been closed to retained earnings.",
    })

    # ── Check 6: Diagnose root cause ─────────────────────────────────────────
    if abs(abs(expected_zero) - abs(cumulative_net_profit)) < max(100, abs(expected_zero) * 0.01):
        issues.append({
            "severity": "critical",
            "type": "diagnosis_pl_not_closed",
            "message": (
                "DIAGNOSED: BS imbalance ≈ cumulative P&L. "
                "The P&L is NOT being closed to retained earnings."
            ),
            "imbalance": expected_zero,
            "cumulative_pl": cumulative_net_profit,
            "recommendation": (
                "The Balance Sheet now includes a synthetic 'Current Period Earnings' line in Equity "
                "that adds the cumulative P&L to equity automatically. This matches Odoo's native "
                "Balance Sheet behavior (account_type='equity_unaffected' is used for closing entries). "
                "To permanently fix: run Year Closing in Odoo → Accounting → Accounting → Year Closing."
            ),
        })
    elif abs(expected_zero) > 1:
        issues.append({
            "severity": "high",
            "type": "undiagnosed_imbalance",
            "message": (
                f"BS imbalance of {expected_zero:,.2f} found but doesn't match cumulative P&L. "
                f"May be caused by: multi-company mixing, currency mismatches, or uncategorized accounts."
            ),
            "imbalance": expected_zero,
            "cumulative_pl": cumulative_net_profit,
        })
    else:
        issues.append({
            "severity": "info",
            "type": "bs_balanced",
            "message": "Balance Sheet is balanced (or within 1 EGP rounding tolerance).",
        })

    return {
        "as_of": as_of.isoformat(),
        "company_id": company_id,
        "summary": {
            "total_accounts": len(all_accounts),
            "bs_accounts": len(bs_accounts),
            "pl_accounts": len(pl_accounts),
            "unknown_type_accounts": len(all_accounts) - len(bs_accounts) - len(pl_accounts),
            "imbalance": expected_zero,
            "cumulative_net_profit": cumulative_net_profit,
        },
        "issues": issues,
    }
