"""
Odoo Discovery Tool — Phase 1 (READ-ONLY)
Run with: python -m src.discovery
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger
from src.utils.audit import AuditLogger
from src.utils.safety_test import run_safety_self_test

load_dotenv()

console = Console()
OUTPUT_DIR = Path("output") / "discovery"

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

CRITICAL_MODULES = [
    "account",
    "account_accountant",
    "sale_management",
    "sale",
    "purchase",
    "stock",
]


def _safe_count(client: OdooReadOnlyClient, model: str, domain: list | None = None) -> int | str:
    try:
        return client.search_count(model, domain or [])
    except Exception as exc:
        logger.warning(f"search_count on {model} failed: {exc}")
        return "N/A"


def _safe_search_read(client: OdooReadOnlyClient, model: str, **kwargs) -> list | None:
    try:
        return client.search_read(model, **kwargs)
    except Exception as exc:
        logger.warning(f"search_read on {model} failed: {exc}")
        return None


def _safe_fields_get(client: OdooReadOnlyClient, model: str) -> dict | None:
    try:
        return client.fields_get(model, attributes=["type", "string", "required"])
    except Exception as exc:
        logger.warning(f"fields_get on {model} failed: {exc}")
        return None


# ------------------------------------------------------------------ #
# Step functions
# ------------------------------------------------------------------ #


def step_banner() -> None:
    console.print()
    console.print(Panel(
        Text("Odoo Discovery Tool — Phase 1 (READ-ONLY)", style="bold cyan", justify="center"),
        border_style="cyan",
        padding=(1, 4),
    ))


def step_database(report: dict, audit_logger=None) -> OdooReadOnlyClient | None:
    logger.section("Step 1 — Database Detection & Connection")
    try:
        client = OdooReadOnlyClient(audit_logger=audit_logger)
        det = client._db_detection_info
        logger.success(f"Database: {client.db} (via {det['strategy_used']})")
        logger.success(f"Connected via {client.api_method.upper()}")
        report["connection"] = {
            "url": client.url,
            "database": client.db,
            "db_strategy": det["strategy_used"],
            "db_candidates_tried": det["candidates_tried"],
            "api_method": client.api_method,
            "uid": client.uid,
        }
        return client
    except Exception as exc:
        logger.error(f"Connection failed: {exc}")
        report["connection"] = {"error": str(exc)}
        return None


def step_version(client: OdooReadOnlyClient, report: dict) -> None:
    logger.section("Step 2 — Odoo Version Info")
    vi = client.version_info
    if not vi:
        logger.warning("No version info available")
        return
    server_version = vi.get("server_version", "unknown")
    series = vi.get("server_serie", "unknown")
    logger.success(f"Odoo version : {server_version}")
    logger.info(f"Series       : {series}")
    logger.info(f"Server TZ    : {vi.get('server_timezone', 'N/A')}")
    logger.info(f"Server time  : {vi.get('server_datetime', 'N/A')}")
    report["version"] = vi


def step_user_companies(client: OdooReadOnlyClient, report: dict) -> dict:
    logger.section("Step 3 — User & Companies")
    summary: dict = {}

    try:
        users = client.read(
            "res.users",
            [client.uid],
            fields=["name", "login", "lang", "tz", "company_id", "company_ids"],
        )
        if users:
            u = users[0]
            logger.success(f"Authenticated as: {u.get('name')} ({u.get('login')})")
            logger.info(f"  Language : {u.get('lang')}")
            logger.info(f"  Timezone : {u.get('tz')}")
            logger.info(f"  Company  : {u.get('company_id')}")
            company_ids = u.get("company_ids", [])
            logger.info(f"  All companies ({len(company_ids)}): {company_ids}")
            summary["user"] = u
    except Exception as exc:
        logger.error(f"Could not read current user: {exc}")

    try:
        companies = client.search_read(
            "res.company",
            fields=["id", "name", "currency_id", "country_id", "vat"],
            limit=100,
        )
        summary["companies"] = companies
        tbl = Table(title="Companies", border_style="blue")
        tbl.add_column("ID", style="dim")
        tbl.add_column("Name")
        tbl.add_column("Currency")
        tbl.add_column("Country")
        tbl.add_column("VAT")
        for c in companies:
            tbl.add_row(
                str(c.get("id")),
                c.get("name", ""),
                str(c.get("currency_id", ["", ""])[1] if isinstance(c.get("currency_id"), list) else c.get("currency_id", "")),
                str(c.get("country_id", ["", ""])[1] if isinstance(c.get("country_id"), list) else c.get("country_id", "")),
                c.get("vat") or "",
            )
        console.print(tbl)
        logger.success(f"{len(companies)} company/companies found")
    except Exception as exc:
        logger.error(f"Could not read companies: {exc}")

    report["user_companies"] = summary
    return summary


def step_installed_modules(client: OdooReadOnlyClient, report: dict) -> dict:
    logger.section("Step 4 — Installed Modules")
    installed_set: set[str] = set()
    l10n_modules: list[dict] = []
    all_modules: list[dict] = []

    try:
        all_modules = client.search_read(
            "ir.module.module",
            domain=[("state", "=", "installed")],
            fields=["name", "shortdesc", "state"],
            limit=1000,
        )
        installed_set = {m["name"] for m in all_modules}
        l10n_modules = [m for m in all_modules if m["name"].startswith("l10n_")]
        logger.success(f"Total installed modules: {len(all_modules)}")
    except Exception as exc:
        logger.error(f"Could not read installed modules: {exc}")

    tbl = Table(title="Critical Modules Status", border_style="blue")
    tbl.add_column("Module", style="cyan")
    tbl.add_column("Status")
    tbl.add_column("Description")
    for mod_name in CRITICAL_MODULES:
        if mod_name in installed_set:
            desc = next((m["shortdesc"] for m in all_modules if m["name"] == mod_name), "")
            tbl.add_row(mod_name, "[green]✓ installed[/green]", desc)
        else:
            tbl.add_row(mod_name, "[red]✗ missing[/red]", "")
    console.print(tbl)

    if l10n_modules:
        logger.success(f"Localization modules ({len(l10n_modules)}): {', '.join(m['name'] for m in l10n_modules)}")
    else:
        logger.warning("No localization (l10n_*) modules found")

    result = {
        "total_installed": len(all_modules),
        "critical": {m: (m in installed_set) for m in CRITICAL_MODULES},
        "l10n_modules": [m["name"] for m in l10n_modules],
        "all_modules": [m["name"] for m in all_modules],
    }
    report["modules"] = result
    return result


def step_accounting_structure(client: OdooReadOnlyClient, report: dict) -> dict:
    logger.section("Step 5 — Accounting Structure")
    result: dict = {}

    # Account count
    total_accounts = _safe_count(client, "account.account")
    logger.success(f"Chart of Accounts: {total_accounts} accounts")
    result["total_accounts"] = total_accounts

    # Detect account_type field (v14+) vs user_type_id (v12/13)
    fields_info = _safe_fields_get(client, "account.account")
    account_type_field = "unknown"
    if fields_info:
        if "account_type" in fields_info:
            account_type_field = "account_type"
        elif "user_type_id" in fields_info:
            account_type_field = "user_type_id"
    result["account_type_field"] = account_type_field
    logger.info(f"Account type field: {account_type_field}")

    # Sample accounts
    sample_fields = ["id", "code", "name"]
    if account_type_field != "unknown":
        sample_fields.append(account_type_field)
    sample_accounts = _safe_search_read(
        client, "account.account", fields=sample_fields, limit=10
    )
    result["sample_accounts"] = sample_accounts or []
    if sample_accounts:
        tbl = Table(title="Sample Accounts (first 10)", border_style="blue")
        tbl.add_column("Code", style="cyan")
        tbl.add_column("Name")
        tbl.add_column("Type")
        for a in sample_accounts:
            acc_type = a.get(account_type_field, "")
            if isinstance(acc_type, list):
                acc_type = acc_type[1]
            tbl.add_row(str(a.get("code", "")), a.get("name", ""), str(acc_type))
        console.print(tbl)

    # Journals
    journals = _safe_search_read(
        client,
        "account.journal",
        fields=["id", "name", "type", "code", "currency_id", "company_id"],
        limit=100,
    )
    result["journals"] = journals or []
    if journals:
        logger.success(f"Journals found: {len(journals)}")
        tbl = Table(title="Journals", border_style="blue")
        tbl.add_column("Code", style="cyan")
        tbl.add_column("Name")
        tbl.add_column("Type")
        tbl.add_column("Currency")
        tbl.add_column("Company")
        for j in journals:
            currency = j.get("currency_id")
            if isinstance(currency, list):
                currency = currency[1]
            company = j.get("company_id")
            if isinstance(company, list):
                company = company[1]
            tbl.add_row(
                j.get("code", ""),
                j.get("name", ""),
                j.get("type", ""),
                str(currency or ""),
                str(company or ""),
            )
        console.print(tbl)

    report["accounting_structure"] = result
    return result


def step_data_volume(client: OdooReadOnlyClient, report: dict) -> dict:
    logger.section("Step 6 — Data Volume")
    result: dict = {}

    counts = [
        ("account.move", "Journal Entries (total)", None),
        ("account.move", "Journal Entries (posted)", [("state", "=", "posted")]),
        ("account.move.line", "Journal Items", None),
        ("res.partner", "Customers", [("customer_rank", ">", 0)]),
        ("res.partner", "Vendors", [("supplier_rank", ">", 0)]),
        ("sale.order", "Sales Orders", None),
        ("purchase.order", "Purchase Orders", None),
    ]

    for model, label, domain in counts:
        val = _safe_count(client, model, domain)
        result[label] = val
        if val == "N/A":
            logger.warning(f"{label}: Not available (module probably not installed)")
        else:
            logger.success(f"{label}: {val:,}" if isinstance(val, int) else f"{label}: {val}")

    report["data_volume"] = result
    return result


def step_field_schema(client: OdooReadOnlyClient, report: dict) -> None:
    logger.section("Step 7 — Field Schema Sample")

    models_to_inspect = {
        "account.move": ["state", "move_type", "date", "partner_id", "amount_total"],
        "account.move.line": ["account_id", "debit", "credit", "balance", "partner_id"],
        "account.account": ["code", "name", "account_type", "user_type_id"],
        "res.partner": ["name", "customer_rank", "supplier_rank", "vat"],
    }

    schema_data: dict = {}
    for model, key_fields in models_to_inspect.items():
        fields = _safe_fields_get(client, model)
        if fields is None:
            logger.warning(f"  {model}: schema not available")
            continue
        schema_data[model] = fields
        logger.success(f"  {model}: {len(fields)} fields total")
        found = [f for f in key_fields if f in fields]
        missing = [f for f in key_fields if f not in fields]
        if found:
            logger.info(f"    Key fields present  : {', '.join(found)}")
        if missing:
            logger.warning(f"    Key fields missing  : {', '.join(missing)}")

    report["field_schema"] = {
        model: {k: {"type": v.get("type"), "string": v.get("string")} for k, v in flds.items()}
        for model, flds in schema_data.items()
    }


def step_date_range(client: OdooReadOnlyClient, report: dict) -> dict:
    logger.section("Step 8 — Data Date Range")
    result: dict = {}
    try:
        oldest = client.search_read(
            "account.move", domain=[], fields=["date"], limit=1, order="date asc"
        )
        newest = client.search_read(
            "account.move", domain=[], fields=["date"], limit=1, order="date desc"
        )
        from_date = oldest[0]["date"] if oldest else "N/A"
        to_date = newest[0]["date"] if newest else "N/A"
        logger.success(f"Data range: {from_date}  →  {to_date}")
        result = {"from": from_date, "to": to_date}
    except Exception as exc:
        logger.error(f"Could not determine date range: {exc}")
        result = {"from": "N/A", "to": "N/A"}
    report["date_range"] = result
    return result


# ------------------------------------------------------------------ #
# Output writers
# ------------------------------------------------------------------ #


def write_json(report: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"discovery_{ts}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def write_markdown(report: dict) -> Path:
    conn = report.get("connection", {})
    version = report.get("version", {})
    uc = report.get("user_companies", {})
    modules = report.get("modules", {})
    acct = report.get("accounting_structure", {})
    vol = report.get("data_volume", {})
    dr = report.get("date_range", {})

    companies = uc.get("companies", [])
    journals = acct.get("journals", [])
    total_accounts = acct.get("total_accounts", "N/A")

    lines: list[str] = [
        "# Odoo Discovery Report — Phase 1",
        "",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "---",
        "",
        "## Connection Info",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| URL | {conn.get('url', 'N/A')} |",
        f"| Database | {conn.get('database', 'N/A')} |",
        f"| Detection strategy | {conn.get('db_strategy', 'N/A')} |",
        f"| API method | {conn.get('api_method', 'N/A')} |",
        f"| Odoo version | {version.get('server_version', 'N/A')} |",
        f"| Server timezone | {version.get('server_timezone', 'N/A')} |",
        "",
        "## User & Companies",
        "",
    ]

    user = uc.get("user", {})
    if user:
        lines += [
            f"- **User**: {user.get('name')} (`{user.get('login')}`)",
            f"- **Language**: {user.get('lang')}",
            f"- **Timezone**: {user.get('tz')}",
            f"- **Primary company**: {user.get('company_id')}",
            "",
        ]

    lines += [f"**{len(companies)} company/companies:**", ""]
    for c in companies:
        currency = c.get("currency_id")
        country = c.get("country_id")
        lines.append(
            f"- {c.get('name')} "
            f"(currency: {currency[1] if isinstance(currency, list) else currency}, "
            f"country: {country[1] if isinstance(country, list) else country}, "
            f"VAT: {c.get('vat') or 'N/A'})"
        )
    lines += ["", "## Installed Modules", ""]

    if modules:
        lines.append("### Critical Modules")
        lines.append("")
        lines.append("| Module | Status |")
        lines.append("|--------|--------|")
        for mod, installed in modules.get("critical", {}).items():
            status = "✓ installed" if installed else "✗ missing"
            lines.append(f"| `{mod}` | {status} |")
        lines.append("")
        l10n = modules.get("l10n_modules", [])
        if l10n:
            lines.append(f"**Localization modules**: {', '.join(f'`{m}`' for m in l10n)}")
        else:
            lines.append("**Localization modules**: none found")
        lines.append("")

    lines += [
        "## Accounting Structure",
        "",
        f"- **Total accounts**: {total_accounts}",
        f"- **Account type field**: `{acct.get('account_type_field', 'unknown')}`",
        f"- **Journals**: {len(journals)}",
        "",
        "### Journals",
        "",
        "| Code | Name | Type |",
        "|------|------|------|",
    ]
    for j in journals:
        lines.append(f"| {j.get('code')} | {j.get('name')} | {j.get('type')} |")

    lines += [
        "",
        "## Data Volume",
        "",
        "| Metric | Count |",
        "|--------|-------|",
    ]
    for label, val in vol.items():
        lines.append(f"| {label} | {val:,} |" if isinstance(val, int) else f"| {label} | {val} |")

    lines += [
        "",
        "## Date Range",
        "",
        f"- **Oldest entry**: {dr.get('from', 'N/A')}",
        f"- **Newest entry**: {dr.get('to', 'N/A')}",
        "",
        "---",
        "",
        "## Recommendations for Phase 2",
        "",
    ]

    recommendations: list[str] = []

    l10n = modules.get("l10n_modules", [])
    if any("l10n_eg" in m for m in l10n):
        recommendations.append(
            "**Egyptian localization detected** → use `l10n_eg`-specific fields and tax groups in reports"
        )
    if len(companies) > 1:
        recommendations.append(
            f"**Multi-company setup ({len(companies)} companies)** → all reports should filter by `company_id`"
        )
    total_moves = vol.get("Journal Entries (total)")
    if isinstance(total_moves, int) and total_moves > 10000:
        recommendations.append(
            f"**Large data volume ({total_moves:,} journal entries)** → use pagination (`limit`/`offset`) in reports"
        )
    atf = acct.get("account_type_field", "unknown")
    if atf == "account_type":
        recommendations.append("**Account type field is `account_type`** (Odoo 14+) → use this field in domain filters")
    elif atf == "user_type_id":
        recommendations.append("**Account type field is `user_type_id`** (Odoo 13 or earlier) → use this field in domain filters")

    if not modules.get("critical", {}).get("account"):
        recommendations.append("**`account` module not installed** → accounting reports will not be possible")

    if not recommendations:
        recommendations.append("No special recommendations — standard configuration detected.")

    for rec in recommendations:
        lines.append(f"- {rec}")

    lines += ["", "---", "_This report was generated by the Odoo Discovery Tool (Phase 1, READ-ONLY)._", ""]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------ #
# Final summary banner
# ------------------------------------------------------------------ #


def print_final_summary(
    report: dict, json_path: Path, md_path: Path, safety_path: Path | None = None
) -> None:
    conn = report.get("connection", {})
    version = report.get("version", {})
    vol = report.get("data_volume", {})
    acct = report.get("accounting_structure", {})
    dr = report.get("date_range", {})
    uc = report.get("user_companies", {})
    modules = report.get("modules", {})

    companies = uc.get("companies", [])
    journals = acct.get("journals", [])
    total_accounts = acct.get("total_accounts", "N/A")

    moves_total = vol.get("Journal Entries (total)", "N/A")
    moves_posted = vol.get("Journal Entries (posted)", "N/A")
    customers = vol.get("Customers", "N/A")
    vendors = vol.get("Vendors", "N/A")

    missing = [m for m, ok in modules.get("critical", {}).items() if not ok]
    missing_str = ", ".join(missing) if missing else "none"

    version_str = version.get("server_version", "unknown")
    method_str = conn.get("api_method", "unknown").upper()
    db_str = conn.get("database", "unknown")

    console.print()
    console.print("═" * 60, style="cyan")

    def row(text: str, style: str = "") -> None:
        console.print(f"  {text}", style=style)

    row(f"✓ Connected to Odoo {version_str} via {method_str}", "green")
    row(f"✓ Database: {db_str} (via {conn.get('db_strategy', '?')})", "green")
    row(f"✓ {len(companies)} company/companies, {len(journals)} journals, {total_accounts} accounts", "green")
    if isinstance(moves_total, int):
        row(f"✓ {moves_total:,} journal entries ({moves_posted:,} posted)", "green")
    else:
        row(f"⚠ Journal entries: {moves_total}", "yellow")
    if isinstance(customers, int) and isinstance(vendors, int):
        row(f"✓ Partners → {customers:,} customers, {vendors:,} vendors", "green")
    row(f"✓ Data range: {dr.get('from', 'N/A')} → {dr.get('to', 'N/A')}", "green")
    if missing:
        row(f"⚠ Missing modules: {missing_str}", "yellow")
    else:
        row("✓ All critical modules installed", "green")
    row(f"✓ JSON report    : {json_path}", "green")
    row(f"✓ Summary        : {md_path}", "green")
    if safety_path:
        row(f"✓ Safety report  : {safety_path}", "green")

    console.print("═" * 60, style="cyan")
    console.print()


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #


def main() -> None:
    report: dict = {"generated_at": datetime.now().isoformat()}

    step_banner()

    # ── Step 0: Pre-flight safety self-test (Layer 6) ──────────────────────
    # Runs WITHOUT connecting to Odoo — verifies all guards are in place.
    # Aborts immediately (SystemExit) if any guard is missing.
    try:
        _test_client = OdooReadOnlyClient(skip_connect=True)
        run_safety_self_test(_test_client)
    except SystemExit:
        raise
    except Exception as exc:
        logger.error(f"Pre-flight self-test setup failed: {exc}")
        sys.exit(1)

    # ── Layer 7: Audit logger ───────────────────────────────────────────────
    audit = AuditLogger()
    # Self-test passed (above) — record it in the audit log
    audit.mark_self_test_passed()
    logger.info(f"Audit log: {audit.log_path}")

    # ── Steps 1–8: Discovery ───────────────────────────────────────────────
    client = step_database(report, audit_logger=audit)
    if client is None:
        sys.exit(1)

    step_version(client, report)
    step_user_companies(client, report)
    step_installed_modules(client, report)
    step_accounting_structure(client, report)
    step_data_volume(client, report)
    step_field_schema(client, report)
    step_date_range(client, report)

    # ── Output: JSON, SUMMARY.md, SAFETY_REPORT.md ─────────────────────────
    json_path = write_json(report)
    md_path = write_markdown(report)
    safety_path = audit.write_safety_report()
    logger.success(f"Safety report: {safety_path}")

    print_final_summary(report, json_path, md_path, safety_path)


if __name__ == "__main__":
    main()
