"""AI tool definitions and dispatcher — strictly read-only."""
from __future__ import annotations

from datetime import date
from typing import Any

from api.models.common import GLFilter, ReportFilter
from api.services import aging as aging_svc
from api.services import balance_sheet as bs_svc
from api.services import cash_bank as cb_svc
from api.services import diagnostics as diag_svc
from api.services import general_ledger as gl_svc
from api.services import profit_loss as pl_svc
from api.services import purchases as purchases_svc
from api.services import sales as sales_svc
from api.services import trial_balance as tb_svc

RECEIVABLE_TYPES = ["asset_receivable"]
PAYABLE_TYPES = ["liability_payable"]

# ---------------------------------------------------------------------------
# OpenAI function-calling schemas (explicit read-only allowlist)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_trial_balance",
            "description": "Fetch the trial balance (all accounts with debit/credit/balance) for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_profit_loss",
            "description": "Fetch the profit & loss statement (revenue, expenses, net profit) for a period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance_sheet",
            "description": "Fetch the balance sheet (assets, liabilities, equity) as of a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "As-of date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["as_of"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_general_ledger",
            "description": "Fetch the transaction history for a specific account in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "integer", "description": "Account ID"},
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                    "limit": {"type": "integer", "description": "Max rows (default 50, max 200)"},
                },
                "required": ["account_id", "date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_aging",
            "description": "Fetch accounts receivable aging report — how much customers owe, bucketed by days overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "As-of date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["as_of"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vendor_aging",
            "description": "Fetch accounts payable aging report — how much is owed to vendors, bucketed by days overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "As-of date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["as_of"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cash_bank",
            "description": "Fetch cash & bank journal balances and movements for a period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales",
            "description": "Fetch the sales report — confirmed sales orders, top customers, monthly trend.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchases",
            "description": "Fetch the purchases report — confirmed purchase orders, top vendors, monthly trend.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_diagnostics",
            "description": "Run balance sheet diagnostic — investigates why assets ≠ liabilities + equity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "As-of date YYYY-MM-DD"},
                    "company_id": {"type": "integer", "description": "Company ID (omit for all)"},
                },
                "required": ["as_of"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_companies",
            "description": "List all available companies in the Odoo database.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_accounts",
            "description": "Search chart of accounts by code or name to find an account ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code or name fragment to search"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": [],
            },
        },
    },
]

# Tool name allowlist — nothing outside this list can be dispatched
_ALLOWED_TOOLS = {s["function"]["name"] for s in TOOL_SCHEMAS}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def execute_tool(name: str, arguments: dict[str, Any], client) -> dict[str, Any]:
    """Execute a named tool against the read-only Odoo client.

    Returns a dict result. Raises ValueError for unknown tool names.
    """
    if name not in _ALLOWED_TOOLS:
        raise ValueError(f"Unknown tool: {name!r}")

    try:
        if name == "get_trial_balance":
            flt = ReportFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            rows = tb_svc.compute_trial_balance(client, flt)
            return {
                "rows": rows,
                "row_count": len(rows),
                "totals": {
                    "debit": round(sum(r["debit"] for r in rows), 2),
                    "credit": round(sum(r["credit"] for r in rows), 2),
                    "balance": round(sum(r["balance"] for r in rows), 2),
                },
            }

        if name == "get_profit_loss":
            flt = ReportFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            return pl_svc.compute_profit_loss(client, flt)

        if name == "get_balance_sheet":
            as_of = arguments["as_of"]
            flt = ReportFilter(
                date_from=as_of,
                date_to=as_of,
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            return bs_svc.compute_balance_sheet(client, flt)

        if name == "get_general_ledger":
            limit = min(int(arguments.get("limit", 50)), 200)
            gl_flt = GLFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                account_id=int(arguments["account_id"]),
                company_id=arguments.get("company_id"),
                posted_only=True,
                offset=0,
                limit=limit,
            )
            return gl_svc.compute_general_ledger(client, gl_flt)

        if name == "get_customer_aging":
            return aging_svc.compute_aging(
                client,
                account_types=RECEIVABLE_TYPES,
                as_of=date.fromisoformat(arguments["as_of"]),
                company_id=arguments.get("company_id"),
                posted_only=True,
            )

        if name == "get_vendor_aging":
            return aging_svc.compute_aging(
                client,
                account_types=PAYABLE_TYPES,
                as_of=date.fromisoformat(arguments["as_of"]),
                company_id=arguments.get("company_id"),
                posted_only=True,
            )

        if name == "get_cash_bank":
            flt = ReportFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            return cb_svc.compute_cash_bank(client, flt)

        if name == "get_sales":
            flt = ReportFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            return sales_svc.compute_sales(client, flt)

        if name == "get_purchases":
            flt = ReportFilter(
                date_from=arguments["date_from"],
                date_to=arguments["date_to"],
                company_id=arguments.get("company_id"),
                posted_only=True,
            )
            return purchases_svc.compute_purchases(client, flt)

        if name == "get_diagnostics":
            return diag_svc.diagnose_balance_sheet(
                client,
                as_of=date.fromisoformat(arguments["as_of"]),
                company_id=arguments.get("company_id"),
                posted_only=True,
            )

        if name == "get_companies":
            return client.search_read(
                "res.company",
                fields=["id", "name", "currency_id"],
                limit=100,
            )

        if name == "search_accounts":
            q = arguments.get("query", "")
            limit = min(int(arguments.get("limit", 20)), 100)
            domain = (
                ["&", ("deprecated", "=", False),
                 "|", ("code", "ilike", q), ("name", "ilike", q)]
                if q
                else [("deprecated", "=", False)]
            )
            return client.search_read(
                "account.account",
                domain=domain,
                fields=["id", "code", "name", "account_type"],
                limit=limit,
                order="code asc",
            )

    except Exception as exc:
        return {"error": str(exc)}

    raise ValueError(f"Unhandled tool: {name!r}")  # should never reach here


# ---------------------------------------------------------------------------
# Result summarizer (for ToolBadge UI)
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    try:
        v = float(value)
        if abs(v) >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"{v / 1_000:.1f}K"
        return f"{v:,.0f}"
    except Exception:
        return str(value)


def summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    try:
        if "error" in result:
            return f"error: {result['error'][:60]}"

        if name == "get_trial_balance":
            n = result.get("row_count", 0)
            return f"{n} accounts"

        if name == "get_profit_loss":
            rev = result.get("revenue", {}).get("total", 0)
            net = result.get("net_profit", 0)
            return f"Rev {_fmt(rev)} · Net {_fmt(net)}"

        if name == "get_balance_sheet":
            assets = result.get("assets", {}).get("total", 0)
            return f"Assets {_fmt(assets)}"

        if name == "get_general_ledger":
            lines = result.get("total_lines", 0)
            return f"{lines} lines"

        if name in ("get_customer_aging", "get_vendor_aging"):
            total = result.get("totals", {}).get("total", 0)
            partners = result.get("totals", {}).get("partner_count", 0)
            return f"{partners} partners · {_fmt(total)}"

        if name == "get_cash_bank":
            bal = result.get("totals", {}).get("ending_balance", 0)
            return f"Balance {_fmt(bal)}"

        if name in ("get_sales", "get_purchases"):
            orders = result.get("total_orders", 0)
            amt = result.get("total_with_tax", 0)
            return f"{orders} orders · {_fmt(amt)}"

        if name == "get_diagnostics":
            issues = len(result.get("issues", []))
            return f"{issues} issues"

        if name == "get_companies":
            return f"{len(result)} companies"

        if name == "search_accounts":
            return f"{len(result)} accounts"

    except Exception:
        pass

    return "done"
