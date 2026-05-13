"""Customer and Vendor Aging — buckets open receivables/payables by overdue days."""
from __future__ import annotations

from datetime import date


def compute_aging(
    client,
    account_types: list[str],
    as_of: date,
    company_id: int | None,
    posted_only: bool,
) -> dict:
    """
    Compute aging buckets for either receivable or payable accounts.

    Buckets:
        not_due  — maturity > as_of_date (or no maturity date)
        1_30     — 1–30 days overdue
        31_60    — 31–60 days overdue
        61_90    — 61–90 days overdue
        91_180   — 91–180 days overdue
        over_180 — more than 180 days overdue
    """
    # 1. Get the relevant accounts
    acc_domain: list = [
        ("account_type", "in", account_types),
        ("deprecated", "=", False),
    ]
    if company_id:
        acc_domain.append(("company_id", "=", company_id))

    accounts = client.search_read(
        "account.account",
        domain=acc_domain,
        fields=["id", "code", "name"],
        limit=500,
    )
    if not accounts:
        return _empty_response(as_of)

    account_ids = [a["id"] for a in accounts]

    # 2. Find unreconciled journal items for these accounts
    domain: list = [
        ("account_id", "in", account_ids),
        ("parent_state", "=", "posted") if posted_only else ("parent_state", "!=", "cancel"),
        ("date", "<=", as_of.isoformat()),
        ("reconciled", "=", False),
        ("partner_id", "!=", False),
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))

    # 3. Aggregate by (partner, maturity_date) using read_group
    grouped = client.execute_kw(
        "account.move.line",
        "read_group",
        [domain, ["amount_residual:sum"], ["partner_id", "date_maturity"]],
        {"lazy": False, "limit": 50000},
    )

    # 4. Bucket each group by overdue days
    bucket_keys = ("not_due", "1_30", "31_60", "61_90", "91_180", "over_180")
    totals: dict[str, float] = {k: 0.0 for k in bucket_keys}
    by_partner: dict[int, dict] = {}

    for g in grouped:
        partner_field = g.get("partner_id")
        if not partner_field:
            continue
        partner_id = partner_field[0] if isinstance(partner_field, (list, tuple)) else partner_field
        partner_name = partner_field[1] if isinstance(partner_field, (list, tuple)) else str(partner_id)

        residual = g.get("amount_residual", 0) or 0.0
        if abs(residual) < 0.01:
            continue

        maturity_raw = g.get("date_maturity")
        if maturity_raw and maturity_raw is not False:
            try:
                maturity_date = date.fromisoformat(str(maturity_raw)[:10])
                days_overdue = (as_of - maturity_date).days
            except ValueError:
                days_overdue = 0
        else:
            days_overdue = 0  # no maturity → treat as not due

        if days_overdue <= 0:
            bucket = "not_due"
        elif days_overdue <= 30:
            bucket = "1_30"
        elif days_overdue <= 60:
            bucket = "31_60"
        elif days_overdue <= 90:
            bucket = "61_90"
        elif days_overdue <= 180:
            bucket = "91_180"
        else:
            bucket = "over_180"

        totals[bucket] += residual

        if partner_id not in by_partner:
            by_partner[partner_id] = {
                "partner_id": partner_id,
                "partner_name": partner_name,
                "total": 0.0,
                **{k: 0.0 for k in bucket_keys},
            }
        by_partner[partner_id][bucket] += residual
        by_partner[partner_id]["total"] += residual

    # 5. Round, sort, cap
    partners = sorted(by_partner.values(), key=lambda x: -x["total"])
    for p in partners:
        for k in list(p.keys()):
            if isinstance(p[k], float):
                p[k] = round(p[k], 2)

    grand_total = round(sum(totals.values()), 2)
    overdue_total = round(sum(v for k, v in totals.items() if k != "not_due"), 2)

    return {
        "as_of": as_of.isoformat(),
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "grand_total": grand_total,
        "overdue_total": overdue_total,
        "partner_count": len(partners),
        "partners": partners[:500],
    }


def _empty_response(as_of: date) -> dict:
    bucket_keys = ("not_due", "1_30", "31_60", "61_90", "91_180", "over_180")
    return {
        "as_of": as_of.isoformat(),
        "totals": {k: 0.0 for k in bucket_keys},
        "grand_total": 0.0,
        "overdue_total": 0.0,
        "partner_count": 0,
        "partners": [],
    }
