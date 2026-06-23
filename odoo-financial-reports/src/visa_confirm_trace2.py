"""
Visa Bank-Confirmation Mechanics — TRACE PASS 2 (READ-ONLY).

Pass 1 found the recent Visa pos.payments all sit in perpetually-OPEN 'تحصيل'
collection sessions, so we pivot: drive the trace from the per-session
account.payment (created only at session CLOSE) on Visa methods, and dissect:
  - the 28 'reconciled' holding-account lines (what did they match against?)
  - which journals move money OUT of the holding account (the confirmation action)
  - which journals move money INTO it (the POS collection)

READ-ONLY. account.move.line filtered to the small holding-account id set only.
Run:  python -m src.visa_confirm_trace2
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger

OUT = Path("output") / "visa_confirm_trace2_raw.json"

# Visa holding accounts discovered in pass 1
HOLDING = [85, 86, 87, 88, 89, 90, 316, 365, 366, 367, 368, 369, 370, 371, 372,
           373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 385, 394,
           395, 396, 397, 398, 399, 400, 961, 962, 16823, 17412, 17416, 17495]

AML = ["id", "account_id", "name", "debit", "credit", "balance", "amount_residual",
       "reconciled", "full_reconcile_id", "matching_number", "matched_debit_ids",
       "matched_credit_ids", "statement_line_id", "payment_id", "move_id", "date",
       "parent_state", "journal_id"]


def safe(label, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{label} failed: {exc}")
        return {"__error__": str(exc)}


def rg(c, model, domain, fields, groupby):
    return c.execute_kw(model, "read_group", [domain, fields, groupby], {"lazy": False})


def main():
    rep = {"generated_at": datetime.now().isoformat()}
    c = OdooReadOnlyClient()
    logger.success(f"Connected uid={c.uid} db={c.db}")

    # Visa method ids (recompute)
    vms = c.search_read("pos.payment.method",
                        [("is_cash_count", "=", False), ("name", "like", "فيزا")],
                        ["id", "name", "journal_id", "outstanding_account_id", "company_id"], 200)
    vm_ids = [m["id"] for m in vms]
    rep["visa_methods_count"] = len(vm_ids)

    # ----------------------------------------------------------------
    # A) Trace 3 real per-session card account.payments (closed sessions)
    # ----------------------------------------------------------------
    logger.section("A — trace per-session Visa account.payment")
    pays = safe("visa account.payments", c.search_read, "account.payment",
                [("pos_payment_method_id", "in", vm_ids), ("pos_session_id", "!=", False),
                 ("state", "=", "posted")],
                ["id", "name", "amount", "journal_id", "outstanding_account_id",
                 "destination_account_id", "is_matched", "is_reconciled", "state",
                 "move_id", "pos_session_id", "pos_payment_method_id", "date"],
                40, 0, "id desc")
    rep["recent_visa_payments"] = pays

    traces = []
    chosen = pays[:3] if isinstance(pays, list) else []
    for p in chosen:
        tr = {"payment": p}
        # the payment's own move lines (debit holding, credit 121100)
        if p.get("move_id"):
            pl = safe(f"pay lines {p['id']}", c.search_read, "account.move.line",
                      [("move_id", "=", p["move_id"][0])], AML, 50, 0, "id")
            tr["payment_move_lines"] = pl
        # the session and its close move
        if p.get("pos_session_id"):
            sess = safe(f"sess {p['id']}", c.search_read, "pos.session",
                        [("id", "=", p["pos_session_id"][0])],
                        ["id", "name", "state", "config_id", "move_id", "stop_at", "rescue"], 1)
            tr["session"] = sess
            if isinstance(sess, list) and sess and sess[0].get("move_id"):
                sml = safe(f"sess move lines {p['id']}", c.search_read, "account.move.line",
                           [("move_id", "=", sess[0]["move_id"][0])], AML, 100, 0, "id")
                tr["session_move_lines"] = sml
        traces.append(tr)
    rep["traces"] = traces

    # ----------------------------------------------------------------
    # B) The 28 'reconciled' holding lines — what did they match against?
    # ----------------------------------------------------------------
    logger.section("B — reconciled holding lines + counterparts")
    base = [("account_id", "in", HOLDING), ("parent_state", "=", "posted")]
    recon = safe("reconciled holding", c.search_read, "account.move.line",
                 base + [("reconciled", "=", True)], AML, 40, 0, "date desc")
    rep["reconciled_holding_lines"] = recon

    # for each, resolve the partial-reconcile counterpart move lines
    counterparts = []
    if isinstance(recon, list):
        for l in recon:
            pr_ids = (l.get("matched_debit_ids") or []) + (l.get("matched_credit_ids") or [])
            cp = {"line_id": l["id"], "account_id": l.get("account_id"),
                  "matching_number": l.get("matching_number"),
                  "partial_ids": pr_ids, "counterpart_lines": []}
            if pr_ids:
                prs = safe(f"partials {l['id']}", c.read, "account.partial.reconcile",
                           pr_ids, ["id", "debit_move_id", "credit_move_id", "amount"])
                cp_line_ids = set()
                if isinstance(prs, list):
                    for pr in prs:
                        for key in ("debit_move_id", "credit_move_id"):
                            if pr.get(key) and pr[key][0] != l["id"]:
                                cp_line_ids.add(pr[key][0])
                if cp_line_ids:
                    cpl = safe(f"cp lines {l['id']}", c.read, "account.move.line",
                               list(cp_line_ids),
                               ["id", "account_id", "name", "debit", "credit",
                                "journal_id", "move_id", "date"])
                    cp["counterpart_lines"] = cpl
            counterparts.append(cp)
    rep["reconciled_counterparts"] = counterparts

    # ----------------------------------------------------------------
    # C) Which journals move money OUT of (credit) and INTO (debit) holding
    # ----------------------------------------------------------------
    logger.section("C — journals in/out of holding accounts")
    rep["holding_credit_by_journal"] = safe(
        "credit by journal", rg, c, "account.move.line",
        base + [("credit", ">", 0)], ["credit"], ["journal_id"])
    rep["holding_debit_by_journal"] = safe(
        "debit by journal", rg, c, "account.move.line",
        base + [("debit", ">", 0)], ["debit"], ["journal_id"])
    # reconciled credit lines grouped by journal (the 'confirmation action' journals)
    rep["holding_recon_credit_by_journal"] = safe(
        "recon credit by journal", rg, c, "account.move.line",
        base + [("credit", ">", 0), ("reconciled", "=", True)], ["credit"], ["journal_id"])

    # sample of credit (money-leaving) lines = candidate confirmation entries
    rep["holding_credit_sample"] = safe(
        "credit sample", c.search_read, "account.move.line",
        base + [("credit", ">", 0)], AML, 12, 0, "date desc")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    logger.success(f"written {OUT}")

    # ---- console ----
    print("\n========= TRACE2 SUMMARY =========")
    print("recent visa account.payments:", len(pays) if isinstance(pays, list) else pays)
    for tr in traces:
        p = tr["payment"]
        print(f"\nPAYMENT {p['id']} {p.get('name')} amt {p.get('amount')} | journal {p.get('journal_id')} "
              f"| out {p.get('outstanding_account_id')} | dest {p.get('destination_account_id')} "
              f"| is_matched {p.get('is_matched')} | is_recon {p.get('is_reconciled')}")
        for l in (tr.get("payment_move_lines") or []):
            if isinstance(l, dict):
                print(f"   PAYline acct {l.get('account_id')} D {l.get('debit')} C {l.get('credit')} "
                      f"recon {l.get('reconciled')} full {l.get('full_reconcile_id')} match# {l.get('matching_number')}")
        for l in (tr.get("session_move_lines") or []):
            if isinstance(l, dict) and (l.get("account_id") and l["account_id"][0] in HOLDING + [16409]):
                print(f"   SESSline acct {l.get('account_id')} D {l.get('debit')} C {l.get('credit')} "
                      f"recon {l.get('reconciled')} full {l.get('full_reconcile_id')} match# {l.get('matching_number')}")
    print("\n--- reconciled holding lines:", len(recon) if isinstance(recon, list) else recon)
    for cp in counterparts:
        print(f"  line {cp['line_id']} acct {cp['account_id']} match# {cp['matching_number']} -> counterparts:")
        for l in (cp.get("counterpart_lines") or []):
            if isinstance(l, dict):
                print(f"      acct {l.get('account_id')} D {l.get('debit')} C {l.get('credit')} "
                      f"journal {l.get('journal_id')} move {l.get('move_id')}")
    print("\n--- credit OUT of holding by journal:")
    for g in (rep["holding_credit_by_journal"] if isinstance(rep["holding_credit_by_journal"], list) else []):
        print(f"   {g.get('journal_id')}  count {g.get('__count')}  credit {g.get('credit')}")
    print("\n--- debit INTO holding by journal:")
    for g in (rep["holding_debit_by_journal"] if isinstance(rep["holding_debit_by_journal"], list) else []):
        print(f"   {g.get('journal_id')}  count {g.get('__count')}  debit {g.get('debit')}")
    print("\n--- RECONCILED credit by journal (the confirmation journals):")
    for g in (rep["holding_recon_credit_by_journal"] if isinstance(rep["holding_recon_credit_by_journal"], list) else []):
        print(f"   {g.get('journal_id')}  count {g.get('__count')}  credit {g.get('credit')}")
    print("==================================\n")


if __name__ == "__main__":
    main()
