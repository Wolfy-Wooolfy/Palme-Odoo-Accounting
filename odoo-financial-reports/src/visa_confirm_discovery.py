"""
Visa Bank-Confirmation Mechanics — FOCUSED READ-ONLY discovery.

Goal: learn the EXACT data mechanics of "the accountant confirmed this Visa
collection actually hit the bank" so a monitoring screen can flag late/missing
confirmations per branch/day.

Traces a few real Visa POS collections end-to-end:
  pos.payment (Visa method)
    -> pos.session.move_id            (debits POS receivable 121100)
    -> pos.session.bank_payment_ids   (account.payment: debit Visa holding acct, credit 121100)
    -> account.move.line on the Visa HOLDING account  <-- the bank-confirmation leg
       reconciled?  full_reconcile_id?  matched against WHAT (bank move / manual JE)?

READ-ONLY: search_count / read_group / search_read (small limits) / read / fields_get.
account.move.line is millions of rows -> NEVER unbounded; always filter by the
small set of holding-account ids and use search_count / limits.

Run:  python -m src.visa_confirm_discovery
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger

OUT = Path("output") / "visa_confirm_discovery_raw.json"


def safe(label, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{label} failed: {exc}")
        return {"__error__": str(exc)}


def rg(client, model, domain, fields, groupby):
    return client.execute_kw(model, "read_group", [domain, fields, groupby], {"lazy": False})


def line_brief(l: dict) -> dict:
    """Trim an account.move.line dict to the recon-relevant fields."""
    return {
        "id": l.get("id"),
        "account_id": l.get("account_id"),
        "name": l.get("name"),
        "debit": l.get("debit"),
        "credit": l.get("credit"),
        "balance": l.get("balance"),
        "amount_residual": l.get("amount_residual"),
        "reconciled": l.get("reconciled"),
        "full_reconcile_id": l.get("full_reconcile_id"),
        "matching_number": l.get("matching_number"),
        "statement_line_id": l.get("statement_line_id"),
        "payment_id": l.get("payment_id"),
        "move_id": l.get("move_id"),
        "date": l.get("date"),
        "parent_state": l.get("parent_state"),
    }


AML_FIELDS = [
    "id", "account_id", "name", "debit", "credit", "balance", "amount_residual",
    "reconciled", "full_reconcile_id", "matching_number", "statement_line_id",
    "payment_id", "move_id", "date", "parent_state", "journal_id",
]


def main():
    report = {"generated_at": datetime.now().isoformat()}
    c = OdooReadOnlyClient()
    report["connection"] = {
        "url": c.url, "db": c.db, "uid": c.uid, "api_method": c.api_method,
        "server_version": c.version_info.get("server_version"),
        "server_datetime": c.version_info.get("server_datetime"),
    }
    logger.success(f"Connected uid={c.uid} db={c.db} v={c.version_info.get('server_version')}")

    # =====================================================================
    # STEP 1 — Visa payment methods, their journals and holding accounts
    # =====================================================================
    logger.section("STEP 1 — Visa methods / journals / holding accounts")
    # Visa methods: non-cash, name containing the Arabic word فيزا
    visa_methods = safe(
        "visa methods", c.search_read, "pos.payment.method",
        [("is_cash_count", "=", False), ("name", "like", "فيزا")],
        ["id", "name", "journal_id", "outstanding_account_id",
         "receivable_account_id", "company_id"],
        200, 0, "company_id, id",
    )
    report["visa_methods"] = visa_methods
    visa_method_ids = [m["id"] for m in visa_methods] if isinstance(visa_methods, list) else []
    visa_journal_ids = sorted({m["journal_id"][0] for m in visa_methods
                               if isinstance(visa_methods, list) and m.get("journal_id")})
    visa_holding_acct_ids = sorted({m["outstanding_account_id"][0] for m in visa_methods
                                    if isinstance(visa_methods, list) and m.get("outstanding_account_id")})
    report["visa_method_ids"] = visa_method_ids
    report["visa_journal_ids"] = visa_journal_ids
    report["visa_holding_acct_ids"] = visa_holding_acct_ids

    # journal details (type should be 'bank')
    report["visa_journals"] = safe(
        "visa journals", c.search_read, "account.journal",
        [("id", "in", visa_journal_ids)],
        ["id", "name", "code", "type", "default_account_id", "suspense_account_id",
         "company_id"], 200,
    )
    # holding account details
    report["visa_holding_accounts"] = safe(
        "visa holding accts", c.search_read, "account.account",
        [("id", "in", visa_holding_acct_ids)],
        ["id", "name", "code", "account_type", "reconcile", "company_id"], 200,
    )
    # method -> (journal, holding account) mapping table (branch attribution proof)
    report["method_attribution_map"] = [
        {"method_id": m["id"], "method": m.get("name"),
         "company": m.get("company_id"),
         "journal": m.get("journal_id"),
         "holding_account": m.get("outstanding_account_id")}
        for m in (visa_methods if isinstance(visa_methods, list) else [])
    ]

    print("\n--- Visa methods:", len(visa_method_ids),
          " journals:", len(visa_journal_ids),
          " distinct holding accts:", len(visa_holding_acct_ids))

    # =====================================================================
    # STEP 2 — pick recent CLOSED sessions that had Visa payments
    # =====================================================================
    logger.section("STEP 2 — recent closed sessions with Visa payments")
    recent_visa_payments = safe(
        "recent visa pp", c.search_read, "pos.payment",
        [("payment_method_id", "in", visa_method_ids), ("amount", ">", 0)],
        ["id", "amount", "payment_date", "session_id", "payment_method_id",
         "pos_order_id", "account_move_id"],
        60, 0, "id desc",
    )
    report["recent_visa_payments_sample"] = recent_visa_payments

    # distinct candidate session ids (preserve order = most recent first)
    cand_session_ids: list[int] = []
    if isinstance(recent_visa_payments, list):
        for p in recent_visa_payments:
            sid = p.get("session_id")
            if sid and sid[0] not in cand_session_ids:
                cand_session_ids.append(sid[0])

    # read those sessions, keep CLOSED ones
    cand_sessions = safe(
        "cand sessions", c.search_read, "pos.session",
        [("id", "in", cand_session_ids), ("state", "=", "closed")],
        ["id", "name", "state", "config_id", "move_id", "bank_payment_ids",
         "start_at", "stop_at", "rescue"],
        60,
    )
    report["candidate_sessions"] = cand_sessions

    # choose up to 3 to trace fully
    traced = []
    chosen = []
    if isinstance(cand_sessions, list):
        # prefer non-rescue sessions that actually have a bank payment + move
        ordered = sorted(
            cand_sessions,
            key=lambda s: (bool(s.get("rescue")),
                           not bool(s.get("bank_payment_ids")),
                           not bool(s.get("move_id"))),
        )
        chosen = ordered[:3]

    # =====================================================================
    # STEP 3 — trace each chosen session end-to-end
    # =====================================================================
    logger.section("STEP 3 — end-to-end trace per session")
    for s in chosen:
        sid = s["id"]
        trace = {"session": s}
        # Visa amount on this session (read_group over pos.payment)
        trace["visa_amount"] = safe(
            f"visa amt {sid}", rg, c, "pos.payment",
            [("session_id", "=", sid), ("payment_method_id", "in", visa_method_ids)],
            ["amount"], ["payment_method_id"],
        )
        # 3a) the session close move lines
        move_id = s.get("move_id")
        if move_id:
            trace["session_move"] = safe(
                f"session move {sid}", c.search_read, "account.move",
                [("id", "=", move_id[0])],
                ["id", "name", "ref", "state", "journal_id", "date"], 1,
            )
            sm_lines = safe(
                f"session move lines {sid}", c.search_read, "account.move.line",
                [("move_id", "=", move_id[0])], AML_FIELDS, 200, 0, "id",
            )
            trace["session_move_lines"] = (
                [line_brief(l) for l in sm_lines] if isinstance(sm_lines, list) else sm_lines
            )
        # 3b) the per-session account.payment(s) for card methods
        bp_ids = s.get("bank_payment_ids") or []
        payments = safe(
            f"bank payments {sid}", c.search_read, "account.payment",
            [("id", "in", bp_ids)],
            ["id", "name", "amount", "journal_id", "outstanding_account_id",
             "destination_account_id", "is_matched", "is_reconciled", "state",
             "move_id", "pos_session_id", "pos_payment_method_id", "date"],
            50,
        )
        trace["bank_payments"] = payments
        # 3c) move lines of each bank payment (which accounts, reconciled?)
        trace["bank_payment_lines"] = {}
        if isinstance(payments, list):
            for p in payments:
                pmove = p.get("move_id")
                if not pmove:
                    continue
                pl = safe(
                    f"payment move lines {p['id']}", c.search_read, "account.move.line",
                    [("move_id", "=", pmove[0])], AML_FIELDS, 50, 0, "id",
                )
                trace["bank_payment_lines"][str(p["id"])] = (
                    [line_brief(l) for l in pl] if isinstance(pl, list) else pl
                )
        traced.append(trace)
    report["traces"] = traced

    # =====================================================================
    # STEP 4 — THE KEY QUESTION: "done" vs "pending" on the holding account
    # =====================================================================
    logger.section("STEP 4 — holding-account reconciliation: done vs pending")
    holding_dom_base = [("account_id", "in", visa_holding_acct_ids),
                        ("parent_state", "=", "posted")]

    step4 = {}
    # counts on the Visa holding accounts
    step4["holding_lines_total"] = safe(
        "holding total", c.search_count, "account.move.line", holding_dom_base)
    step4["holding_lines_reconciled"] = safe(
        "holding recon", c.search_count, "account.move.line",
        holding_dom_base + [("reconciled", "=", True)])
    step4["holding_lines_not_reconciled"] = safe(
        "holding not recon", c.search_count, "account.move.line",
        holding_dom_base + [("reconciled", "=", False)])
    # only debit side (the actual Visa collections landing in the holding acct)
    step4["holding_debit_lines_total"] = safe(
        "holding debit total", c.search_count, "account.move.line",
        holding_dom_base + [("debit", ">", 0)])
    step4["holding_debit_reconciled"] = safe(
        "holding debit recon", c.search_count, "account.move.line",
        holding_dom_base + [("debit", ">", 0), ("reconciled", "=", True)])
    step4["holding_debit_not_reconciled"] = safe(
        "holding debit notrecon", c.search_count, "account.move.line",
        holding_dom_base + [("debit", ">", 0), ("reconciled", "=", False)])

    # oldest / newest PENDING (unreconciled) holding-account line
    step4["oldest_pending"] = safe(
        "oldest pending", c.search_read, "account.move.line",
        holding_dom_base + [("reconciled", "=", False)],
        ["id", "date", "name", "debit", "credit", "amount_residual", "account_id", "move_id"],
        1, 0, "date asc",
    )
    step4["newest_pending"] = safe(
        "newest pending", c.search_read, "account.move.line",
        holding_dom_base + [("reconciled", "=", False)],
        ["id", "date", "name", "debit", "credit", "amount_residual", "account_id", "move_id"],
        1, 0, "date desc",
    )

    # THE "DONE" PATTERN: a holding-account line that IS reconciled.
    done_lines = safe(
        "done holding lines", c.search_read, "account.move.line",
        holding_dom_base + [("reconciled", "=", True), ("full_reconcile_id", "!=", False)],
        AML_FIELDS, 8, 0, "date desc",
    )
    step4["done_holding_lines_sample"] = (
        [line_brief(l) for l in done_lines] if isinstance(done_lines, list) else done_lines
    )

    # For the first few "done" lines: pull the FULL reconciliation group and
    # identify the COUNTERPART (what cleared the holding account = the bank side).
    step4["done_reconciliation_groups"] = []
    if isinstance(done_lines, list):
        for dl in done_lines[:4]:
            fr = dl.get("full_reconcile_id")
            if not fr:
                continue
            group_lines = safe(
                f"recon group {fr[0]}", c.search_read, "account.move.line",
                [("full_reconcile_id", "=", fr[0])], AML_FIELDS, 50, 0, "id",
            )
            group = [line_brief(l) for l in group_lines] if isinstance(group_lines, list) else group_lines
            # counterpart = the line(s) NOT on a Visa holding account
            counterpart_moves = []
            if isinstance(group_lines, list):
                cp_move_ids = sorted({l["move_id"][0] for l in group_lines
                                      if l.get("move_id")
                                      and (not l.get("account_id")
                                           or l["account_id"][0] not in visa_holding_acct_ids)})
                if cp_move_ids:
                    counterpart_moves = safe(
                        f"cp moves {fr[0]}", c.search_read, "account.move",
                        [("id", "in", cp_move_ids)],
                        ["id", "name", "ref", "date", "journal_id", "move_type", "state"],
                        50,
                    )
            step4["done_reconciliation_groups"].append({
                "trigger_line": line_brief(dl),
                "full_reconcile_id": fr,
                "group_lines": group,
                "counterpart_moves": counterpart_moves,
            })

    # THE "PENDING" PATTERN: an unreconciled debit holding-account line
    pending_lines = safe(
        "pending holding lines", c.search_read, "account.move.line",
        holding_dom_base + [("reconciled", "=", False), ("debit", ">", 0)],
        AML_FIELDS, 8, 0, "date desc",
    )
    step4["pending_holding_lines_sample"] = (
        [line_brief(l) for l in pending_lines] if isinstance(pending_lines, list) else pending_lines
    )
    report["step4_done_vs_pending"] = step4

    # =====================================================================
    # STEP 5 — which journals settle the holding account (the "done" side)
    # =====================================================================
    logger.section("STEP 5 — what journals/accounts clear the holding account")
    # Look at reconciled holding-account CREDIT lines (the settlement leg out of holding)
    settle_credit = safe(
        "settle credit lines", c.search_read, "account.move.line",
        holding_dom_base + [("reconciled", "=", True), ("credit", ">", 0)],
        AML_FIELDS, 10, 0, "date desc",
    )
    report["settlement_credit_lines_sample"] = (
        [line_brief(l) for l in settle_credit] if isinstance(settle_credit, list) else settle_credit
    )

    # =====================================================================
    # STEP 6 — backlog sizing, per holding account
    # =====================================================================
    logger.section("STEP 6 — backlog per holding account")
    backlog = []
    for acct_id in visa_holding_acct_ids:
        tot = safe(f"acct tot {acct_id}", c.search_count, "account.move.line",
                   [("account_id", "=", acct_id), ("parent_state", "=", "posted")])
        rec = safe(f"acct rec {acct_id}", c.search_count, "account.move.line",
                   [("account_id", "=", acct_id), ("parent_state", "=", "posted"),
                    ("reconciled", "=", True)])
        notrec = safe(f"acct nr {acct_id}", c.search_count, "account.move.line",
                      [("account_id", "=", acct_id), ("parent_state", "=", "posted"),
                       ("reconciled", "=", False)])
        oldest = safe(f"acct oldest {acct_id}", c.search_read, "account.move.line",
                      [("account_id", "=", acct_id), ("parent_state", "=", "posted"),
                       ("reconciled", "=", False)],
                      ["date"], 1, 0, "date asc")
        backlog.append({
            "account_id": acct_id,
            "total": tot, "reconciled": rec, "not_reconciled": notrec,
            "oldest_pending_date": (oldest[0]["date"] if isinstance(oldest, list) and oldest else None),
        })
    report["backlog_per_holding_account"] = backlog

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    logger.success(f"Raw data written to {OUT}")

    # ------------------------- console summary -------------------------
    print("\n================ VISA CONFIRM SUMMARY ================")
    print("Visa methods:", len(visa_method_ids),
          "| journals:", len(visa_journal_ids),
          "| holding accts:", len(visa_holding_acct_ids), visa_holding_acct_ids)
    print("\nHolding-account move lines (posted):")
    print("  total:", step4["holding_lines_total"],
          "reconciled:", step4["holding_lines_reconciled"],
          "NOT reconciled:", step4["holding_lines_not_reconciled"])
    print("  DEBIT lines (collections): total:", step4["holding_debit_lines_total"],
          "recon:", step4["holding_debit_reconciled"],
          "NOT recon:", step4["holding_debit_not_reconciled"])
    print("  oldest pending:", step4["oldest_pending"])
    print("  newest pending:", step4["newest_pending"])
    print("\nDONE reconciliation groups (counterpart = bank side):")
    for g in step4.get("done_reconciliation_groups", []):
        print("  full_reconcile_id:", g["full_reconcile_id"])
        for cp in (g.get("counterpart_moves") or []):
            if isinstance(cp, dict):
                print("    counterpart move:", cp.get("name"), "| journal:", cp.get("journal_id"),
                      "| type:", cp.get("move_type"), "| ref:", cp.get("ref"))
    print("\nBacklog per holding account:")
    for b in backlog:
        print("  acct", b["account_id"], "total", b["total"], "rec", b["reconciled"],
              "pending", b["not_reconciled"], "oldest_pending", b["oldest_pending_date"])
    print("=====================================================\n")


if __name__ == "__main__":
    main()
