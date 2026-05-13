"""Purchases Report — order totals, top vendors, monthly trend."""
from __future__ import annotations

from api.models.common import ReportFilter


def compute_purchases(client, filters: ReportFilter) -> dict:
    domain: list = [
        ("date_order", ">=", filters.date_from.isoformat()),
        ("date_order", "<=", filters.date_to.isoformat() + " 23:59:59"),
        ("state", "in", ["purchase", "done"]),
    ]
    if filters.company_id:
        domain.append(("company_id", "=", filters.company_id))

    total_count = client.search_count("purchase.order", domain)
    if total_count == 0:
        return _empty_response(filters)

    summary_groups = client.execute_kw(
        "purchase.order", "read_group",
        [domain, ["amount_untaxed:sum", "amount_total:sum"], []],
        {"lazy": False},
    )
    total_untaxed = summary_groups[0].get("amount_untaxed", 0) or 0.0 if summary_groups else 0.0
    total_with_tax = summary_groups[0].get("amount_total", 0) or 0.0 if summary_groups else 0.0

    # Top vendors
    by_partner = client.execute_kw(
        "purchase.order", "read_group",
        [domain, ["amount_total:sum"], ["partner_id"]],
        {"lazy": False, "limit": 20},
    )
    top_vendors = []
    for g in by_partner:
        partner = g.get("partner_id")
        if not partner:
            continue
        top_vendors.append({
            "partner_id": partner[0] if isinstance(partner, (list, tuple)) else partner,
            "partner_name": partner[1] if isinstance(partner, (list, tuple)) else str(partner),
            "total_purchases": round(g.get("amount_total", 0) or 0.0, 2),
            "order_count": g.get("__count", 0),
        })
    top_vendors.sort(key=lambda x: -x["total_purchases"])

    # Monthly trend
    by_month = client.execute_kw(
        "purchase.order", "read_group",
        [domain, ["amount_total:sum"], ["date_order:month"]],
        {"lazy": False},
    )
    monthly_trend = []
    for g in by_month:
        monthly_trend.append({
            "month": str(g.get("date_order:month", "")),
            "amount": round(g.get("amount_total", 0) or 0.0, 2),
            "order_count": g.get("__count", 0),
        })

    return {
        "period": {
            "from": filters.date_from.isoformat(),
            "to": filters.date_to.isoformat(),
        },
        "summary": {
            "total_orders": total_count,
            "total_untaxed": round(total_untaxed, 2),
            "total_with_tax": round(total_with_tax, 2),
            "average_order_value": round(total_with_tax / total_count, 2) if total_count else 0.0,
        },
        "top_vendors": top_vendors,
        "monthly_trend": monthly_trend,
    }


def _empty_response(filters: ReportFilter) -> dict:
    return {
        "period": {"from": filters.date_from.isoformat(), "to": filters.date_to.isoformat()},
        "summary": {"total_orders": 0, "total_untaxed": 0.0, "total_with_tax": 0.0, "average_order_value": 0.0},
        "top_vendors": [],
        "monthly_trend": [],
    }
