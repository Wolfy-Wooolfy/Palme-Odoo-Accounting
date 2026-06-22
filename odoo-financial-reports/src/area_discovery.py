"""
Area Discovery (READ-ONLY) — POS sessions, card reconciliation, bank movements,
purchase cycle.

Single connection, read-only only (search_count / read_group / search_read /
fields_get). Dumps everything to output/area_discovery_raw.json and prints a
readable summary. Does NOT write to Odoo and does NOT modify any project file.

Run: python -m src.area_discovery
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger

OUT = Path("output") / "area_discovery_raw.json"

# ---------------------------------------------------------------- helpers ----


def safe(label, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{label} failed: {exc}")
        return {"__error__": str(exc)}


def fields_brief(client, model, focus=None):
    """fields_get trimmed to name/type/string/relation/required/store.
    Returns (focus_fields_dict, all_field_names_list)."""
    try:
        fg = client.fields_get(model)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}, []
    brief = {}
    for fname, meta in fg.items():
        brief[fname] = {
            "type": meta.get("type"),
            "string": meta.get("string"),
            "relation": meta.get("relation"),
            "required": meta.get("required"),
            "store": meta.get("store"),
            "selection": meta.get("selection") if meta.get("type") == "selection" else None,
        }
    out = {"all_field_names": sorted(brief.keys()), "field_count": len(brief)}
    if focus:
        out["focus"] = {f: brief.get(f, "MISSING") for f in focus}
    else:
        out["fields"] = brief
    return out, sorted(brief.keys())


def read_group(client, model, domain, fields, groupby):
    return client.execute_kw(
        model, "read_group", [domain, fields, groupby], {"lazy": False}
    )


# ---------------------------------------------------------------- main ----


def main():
    report = {"generated_at": datetime.now().isoformat()}
    c = OdooReadOnlyClient()
    report["connection"] = {
        "url": c.url,
        "db": c.db,
        "uid": c.uid,
        "api_method": c.api_method,
        "server_version": c.version_info.get("server_version"),
        "server_datetime": c.version_info.get("server_datetime"),
        "server_timezone": c.version_info.get("server_timezone"),
    }
    logger.success(f"Connected uid={c.uid} db={c.db} v={c.version_info.get('server_version')}")

    # ============================================================= AREA 1 ===
    logger.section("AREA 1 — POS Sessions")
    a1 = {}
    a1["pos_session_fields"], _ = fields_brief(
        c, "pos.session",
        focus=["state", "start_at", "stop_at", "config_id", "user_id",
               "name", "cash_register_balance_start", "cash_register_balance_end",
               "cash_register_balance_end_real", "cash_register_difference",
               "cash_real_transaction", "currency_id", "company_id",
               "order_count", "total_payments_amount", "payment_method_ids",
               "rescue", "move_id", "bank_payment_ids", "statement_line_ids"],
    )
    a1["pos_session_total"] = safe("ps total", c.search_count, "pos.session")
    a1["pos_session_by_state"] = safe(
        "ps by state", read_group, c, "pos.session", [], ["state"], ["state"]
    )
    a1["pos_session_open_count"] = safe(
        "ps open", c.search_count, "pos.session", [("state", "=", "opened")]
    )
    a1["pos_session_closing_count"] = safe(
        "ps closing", c.search_count, "pos.session", [("state", "=", "closing_control")]
    )
    a1["open_sessions_sample"] = safe(
        "open sample", c.search_read, "pos.session",
        [("state", "in", ["opened", "closing_control"])],
        ["id", "name", "state", "config_id", "user_id", "start_at", "stop_at",
         "order_count", "cash_register_balance_start"],
        50, 0, "start_at asc",
    )
    a1["pos_config_fields"], _ = fields_brief(
        c, "pos.config",
        focus=["name", "active", "current_session_id", "current_session_state",
               "journal_id", "invoice_journal_id", "payment_method_ids",
               "company_id", "module_pos_restaurant"],
    )
    a1["pos_configs"] = safe(
        "pos configs", c.search_read, "pos.config", [],
        ["id", "name", "active", "current_session_id", "current_session_state",
         "journal_id", "invoice_journal_id", "payment_method_ids", "company_id"],
        100,
    )

    # ============================================================= AREA 2 ===
    logger.section("AREA 2 — POS Card / Visa payments & reconciliation")
    a2 = {}
    a2["pos_payment_method_fields"], _ = fields_brief(
        c, "pos.payment.method",
        focus=["name", "type", "is_cash_count", "journal_id",
               "receivable_account_id", "outstanding_account_id",
               "split_transactions", "use_payment_terminal", "company_id",
               "payment_method_type"],
    )
    a2["pos_payment_methods"] = safe(
        "ppm list", c.search_read, "pos.payment.method", [],
        ["id", "name", "is_cash_count", "journal_id", "receivable_account_id",
         "outstanding_account_id", "split_transactions", "use_payment_terminal",
         "company_id"],
        100,
    )
    a2["pos_payment_fields"], _ = fields_brief(
        c, "pos.payment",
        focus=["pos_order_id", "payment_method_id", "amount", "payment_date",
               "card_type", "cardholder_name", "transaction_id", "session_id",
               "currency_id", "account_move_id", "is_change", "name",
               "card_brand", "card_no", "payment_ref_no", "payment_status"],
    )
    a2["pos_payment_total"] = safe("pp total", c.search_count, "pos.payment")
    a2["pos_payment_by_method"] = safe(
        "pp by method", read_group, c, "pos.payment", [],
        ["payment_method_id", "amount"], ["payment_method_id"],
    )
    # sample payments per non-cash method (card-like)
    a2["card_payment_samples"] = {}
    pms = a2.get("pos_payment_methods")
    if isinstance(pms, list):
        for pm in pms:
            if not pm.get("is_cash_count"):  # non-cash = likely card/bank
                pid = pm["id"]
                a2["card_payment_samples"][f"{pid}:{pm.get('name')}"] = safe(
                    f"pp sample {pid}", c.search_read, "pos.payment",
                    [("payment_method_id", "=", pid)],
                    ["id", "name", "amount", "payment_date", "card_type",
                     "cardholder_name", "transaction_id", "pos_order_id",
                     "session_id", "account_move_id", "payment_method_id"],
                    5, 0, "id desc",
                )
    a2["pos_order_fields"], _ = fields_brief(
        c, "pos.order",
        focus=["name", "session_id", "payment_ids", "account_move",
               "state", "amount_total", "partner_id", "config_id"],
    )
    a2["aml_recon_fields"], _ = fields_brief(
        c, "account.move.line",
        focus=["reconciled", "full_reconcile_id", "matched_debit_ids",
               "matched_credit_ids", "amount_residual", "amount_residual_currency",
               "account_id", "statement_line_id", "payment_id", "move_id",
               "matching_number"],
    )

    # ============================================================= AREA 3 ===
    logger.section("AREA 3 — Bank movements & gaps")
    a3 = {}
    a3["bank_journal_fields"], _ = fields_brief(
        c, "account.journal",
        focus=["name", "code", "type", "bank_account_id", "default_account_id",
               "suspense_account_id", "currency_id", "company_id",
               "bank_statements_source"],
    )
    a3["bank_journals"] = safe(
        "bank journals", c.search_read, "account.journal",
        [("type", "=", "bank")],
        ["id", "name", "code", "type", "bank_account_id", "default_account_id",
         "suspense_account_id", "currency_id", "company_id"],
        100,
    )
    a3["cash_journals"] = safe(
        "cash journals", c.search_read, "account.journal",
        [("type", "=", "cash")],
        ["id", "name", "code", "type", "default_account_id", "company_id"],
        100,
    )
    a3["bank_statement_fields"], _ = fields_brief(
        c, "account.bank.statement",
        focus=["name", "date", "journal_id", "balance_start", "balance_end_real",
               "balance_end", "line_ids", "company_id"],
    )
    a3["bank_statement_total"] = safe("bs total", c.search_count, "account.bank.statement")
    a3["bsl_fields"], _ = fields_brief(
        c, "account.bank.statement.line",
        focus=["is_reconciled", "amount", "date", "payment_ref", "partner_id",
               "journal_id", "statement_id", "account_number", "move_id",
               "amount_residual", "currency_id", "company_id", "transaction_type",
               "narration"],
    )
    a3["bsl_total"] = safe("bsl total", c.search_count, "account.bank.statement.line")
    a3["bsl_reconciled"] = safe(
        "bsl recon", c.search_count, "account.bank.statement.line",
        [("is_reconciled", "=", True)],
    )
    a3["bsl_not_reconciled"] = safe(
        "bsl notrecon", c.search_count, "account.bank.statement.line",
        [("is_reconciled", "=", False)],
    )
    a3["bsl_by_journal"] = safe(
        "bsl by journal", read_group, c, "account.bank.statement.line", [],
        ["journal_id"], ["journal_id"],
    )
    a3["bsl_sample"] = safe(
        "bsl sample", c.search_read, "account.bank.statement.line", [],
        ["id", "date", "payment_ref", "amount", "is_reconciled", "partner_id",
         "journal_id", "statement_id", "move_id"],
        10, 0, "date desc",
    )
    a3["account_payment_fields"], _ = fields_brief(
        c, "account.payment",
        focus=["name", "amount", "payment_type", "partner_type", "journal_id",
               "is_reconciled", "is_matched", "state", "date",
               "outstanding_account_id", "destination_account_id", "move_id",
               "reconciled_invoice_ids", "reconciled_bill_ids"],
    )
    a3["account_payment_total"] = safe("ap total", c.search_count, "account.payment")

    # ============================================================= AREA 4 ===
    logger.section("AREA 4 — Purchase cycle (PO -> Receipt -> Bill)")
    a4 = {}
    a4["purchase_order_fields"], _ = fields_brief(
        c, "purchase.order",
        focus=["name", "state", "partner_id", "picking_ids", "invoice_ids",
               "invoice_count", "invoice_status", "amount_total", "order_line",
               "picking_count", "company_id", "date_order"],
    )
    a4["po_total"] = safe("po total", c.search_count, "purchase.order")
    a4["po_by_invoice_status"] = safe(
        "po by inv status", read_group, c, "purchase.order", [],
        ["invoice_status"], ["invoice_status"],
    )
    a4["po_by_state"] = safe(
        "po by state", read_group, c, "purchase.order", [],
        ["state"], ["state"],
    )
    a4["po_zero_bills"] = safe(
        "po zero bills", c.search_count, "purchase.order",
        [("invoice_ids", "=", False)],
    )
    a4["po_has_bills"] = safe(
        "po has bills", c.search_count, "purchase.order",
        [("invoice_ids", "!=", False)],
    )
    # distribution by invoice_count (try read_group; may fail if not stored)
    a4["po_by_invoice_count"] = safe(
        "po by inv count", read_group, c, "purchase.order", [],
        ["invoice_count"], ["invoice_count"],
    )
    a4["stock_picking_fields"], _ = fields_brief(
        c, "stock.picking",
        focus=["name", "origin", "purchase_id", "state", "picking_type_id",
               "picking_type_code", "partner_id", "scheduled_date",
               "date_done", "company_id"],
    )
    a4["picking_total"] = safe("picking total", c.search_count, "stock.picking")
    a4["picking_incoming"] = safe(
        "picking incoming", c.search_count, "stock.picking",
        [("picking_type_code", "=", "incoming")],
    )
    a4["picking_from_po"] = safe(
        "picking from po", c.search_count, "stock.picking",
        [("purchase_id", "!=", False)],
    )
    a4["account_move_purchase_fields"], _ = fields_brief(
        c, "account.move",
        focus=["name", "move_type", "invoice_origin", "partner_id", "state",
               "amount_total", "invoice_date", "purchase_id",
               "purchase_order_count", "journal_id", "company_id", "ref"],
    )
    a4["aml_purchase_link_fields"], _ = fields_brief(
        c, "account.move.line",
        focus=["purchase_line_id", "purchase_order_id", "move_id", "product_id"],
    )
    a4["bill_total"] = safe(
        "bill total", c.search_count, "account.move",
        [("move_type", "=", "in_invoice")],
    )
    a4["refund_total"] = safe(
        "refund total", c.search_count, "account.move",
        [("move_type", "=", "in_refund")],
    )
    a4["bill_with_origin"] = safe(
        "bill w/origin", c.search_count, "account.move",
        [("move_type", "=", "in_invoice"), ("invoice_origin", "!=", False)],
    )

    # samples
    a4["po_sample"] = safe(
        "po sample", c.search_read, "purchase.order", [],
        ["id", "name", "state", "invoice_status", "invoice_count", "picking_ids",
         "invoice_ids", "partner_id", "amount_total"],
        5, 0, "id desc",
    )
    a4["picking_sample"] = safe(
        "picking sample", c.search_read, "stock.picking",
        [("purchase_id", "!=", False)],
        ["id", "name", "origin", "purchase_id", "state", "picking_type_id"],
        5, 0, "id desc",
    )
    a4["bill_sample"] = safe(
        "bill sample", c.search_read, "account.move",
        [("move_type", "=", "in_invoice")],
        ["id", "name", "invoice_origin", "partner_id", "state", "amount_total",
         "invoice_date", "ref"],
        5, 0, "id desc",
    )

    report["area1_pos_sessions"] = a1
    report["area2_card_payments"] = a2
    report["area3_bank"] = a3
    report["area4_purchase"] = a4

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.success(f"Raw data written to {OUT}")

    # ----- concise console summary -----
    print("\n================ SUMMARY ================")
    print("AREA1 pos.session total:", a1["pos_session_total"])
    print("AREA1 by state:", a1["pos_session_by_state"])
    print("AREA1 open count:", a1["pos_session_open_count"],
          "closing:", a1["pos_session_closing_count"])
    print("AREA1 pos.config count:",
          len(a1["pos_configs"]) if isinstance(a1["pos_configs"], list) else a1["pos_configs"])
    print("AREA2 payment methods:",
          [(m.get("name"), m.get("is_cash_count"), m.get("journal_id"))
           for m in a2["pos_payment_methods"]] if isinstance(a2["pos_payment_methods"], list)
          else a2["pos_payment_methods"])
    print("AREA2 pos.payment total:", a2["pos_payment_total"])
    print("AREA3 bank journals:",
          [(j.get("code"), j.get("name")) for j in a3["bank_journals"]]
          if isinstance(a3["bank_journals"], list) else a3["bank_journals"])
    print("AREA3 bsl total:", a3["bsl_total"], "recon:", a3["bsl_reconciled"],
          "not:", a3["bsl_not_reconciled"], "statements:", a3["bank_statement_total"])
    print("AREA4 PO total:", a4["po_total"], "zero_bills:", a4["po_zero_bills"],
          "has_bills:", a4["po_has_bills"])
    print("AREA4 by invoice_status:", a4["po_by_invoice_status"])
    print("AREA4 by invoice_count:", a4["po_by_invoice_count"])
    print("AREA4 bills(in_invoice):", a4["bill_total"], "refunds:", a4["refund_total"],
          "pickings from PO:", a4["picking_from_po"])
    print("=========================================\n")


if __name__ == "__main__":
    main()
