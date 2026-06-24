"""
Area-3 FOCUSED discovery (READ-ONLY) — Bank movements & gaps.

Pre-build follow-up before the Area-3 screen. Answers the user's real question:
"see ALL bank movements + whether there are GAPS or everything is reconciled,
given everything is supposed to be recorded." NO screen/endpoint — report only.

Builds on DISCOVERY_REPORT.md "AREA 3" findings (verify, then go deeper):
  - account.bank.statement UNUSED (0) -> iterate statement *lines*.
  - 938 bank-type lines (all reconciled) vs 1,738 open cash lines.
  - bigger gap lives in account.payment (4,457 unreconciled / 737 unmatched).
  - cards bypass statement lines (Area-2 holding accounts).

Field-store reality (probed): on account.payment, state/journal_id/company_id/date
are store=False; on account.bank.statement.line, journal_id/company_id/date are
store=False. So we CANNOT read_group by those -> loop the tiny company/journal sets
with search_count, and use read_group(domain, ['amount'], []) for scalar sums.
is_reconciled / is_matched / amount / move_id ARE stored.

READ-ONLY: search_count / read_group / bounded search_read only.
Run:  PYTHONIOENCODING=utf-8 python -m src.area3_bank_discovery
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger

OUT = Path("output") / "area3_bank_discovery_raw.json"

COMPANIES = {1: "Palme", 2: "##Manufacture Palme##", 3: "#بالميه#."}


def safe(label, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{label} failed: {exc}")
        return {"__error__": str(exc)}


def rg(c, model, domain, fields, groupby, **kw):
    kw.setdefault("lazy", False)
    return c.execute_kw(model, "read_group", [domain, fields, groupby], kw)


def sum_amount(c, model, domain, field="amount"):
    """Scalar sum + count for a domain, via read_group with empty groupby."""
    r = safe("sum", rg, c, model, domain, [f"{field}:sum"], [])
    if isinstance(r, list) and r:
        return {"count": r[0].get("__count"), "sum": r[0].get(field)}
    return {"count": None, "sum": None, "raw": r}


def main():
    rep = {"generated_at": datetime.now().isoformat()}
    c = OdooReadOnlyClient()
    srv = c.version_info.get("server_datetime")
    rep["connection"] = {"db": c.db, "uid": c.uid, "server_datetime": srv}
    logger.success(f"Connected uid={c.uid} db={c.db} srv={srv}")

    # ====================================================================
    # STEP 1 — BANK JOURNAL INVENTORY (real bank vs Visa-holding)
    # ====================================================================
    logger.section("STEP 1 — bank journal inventory")
    jrns = safe("bank journals", c.search_read, "account.journal",
                [("type", "=", "bank")],
                ["id", "code", "name", "company_id", "default_account_id",
                 "bank_account_id", "suspense_account_id", "currency_id", "active"],
                500, 0, "company_id, code")
    rep["bank_journals_raw"] = jrns

    # read the default accounts to classify (account_type/code/name/reconcile)
    def_ids = sorted({j["default_account_id"][0] for j in jrns
                      if isinstance(jrns, list) and j.get("default_account_id")})
    susp_ids_from_jrn = sorted({j["suspense_account_id"][0] for j in jrns
                                if isinstance(jrns, list) and j.get("suspense_account_id")})
    accts = safe("default accts", c.search_read, "account.account",
                 [("id", "in", def_ids)],
                 ["id", "code", "name", "account_type", "reconcile", "company_id"], 500)
    acct_by_id = {a["id"]: a for a in accts} if isinstance(accts, list) else {}
    rep["default_accounts"] = accts

    # classify each bank journal: VISA-holding vs REAL bank
    real_bank, visa_hold = [], []
    for j in (jrns if isinstance(jrns, list) else []):
        da = j.get("default_account_id")
        acc = acct_by_id.get(da[0]) if da else None
        code = (j.get("code") or "")
        nm = (j.get("name") or "")
        accname = (acc or {}).get("name", "") or ""
        is_visa = (
            code.upper().startswith("VIS")
            or "فيزا" in nm or "فيزا" in accname
            or "visa" in nm.lower() or "visa" in accname.lower()
        )
        has_bank_acct = bool(j.get("bank_account_id"))
        row = {
            "id": j["id"], "code": code, "name": nm,
            "company_id": j.get("company_id"),
            "default_account": [acc["code"], acc["name"], acc["account_type"]] if acc else None,
            "default_account_type": (acc or {}).get("account_type"),
            "bank_account_id": j.get("bank_account_id"),
            "suspense_account_id": j.get("suspense_account_id"),
            "active": j.get("active"),
            "currency_id": j.get("currency_id"),
        }
        (visa_hold if (is_visa and not has_bank_acct) else real_bank).append(row)

    rep["real_bank_journals"] = real_bank
    rep["visa_holding_journals_count"] = len(visa_hold)
    rep["visa_holding_journals_sample"] = visa_hold[:8]
    real_ids = [r["id"] for r in real_bank]
    visa_ids = [r["id"] for r in visa_hold]
    rep["real_bank_journal_ids"] = real_ids
    rep["visa_holding_journal_ids"] = visa_ids
    logger.success(f"{len(jrns)} bank-type journals -> {len(real_bank)} REAL bank, "
                   f"{len(visa_hold)} Visa-holding")

    # per-company real-bank journal grouping
    rbper = defaultdict(list)
    for r in real_bank:
        cid = r["company_id"][0] if r["company_id"] else None
        rbper[cid].append(f"{r['code']} {r['name']}")
    rep["real_bank_journals_per_company"] = {str(k): v for k, v in rbper.items()}

    # cash journals (context)
    rep["cash_journal_count"] = safe("cash jrn count", c.search_count,
                                     "account.journal", [("type", "=", "cash")])

    # ====================================================================
    # STEP 2 — does domain filter / order work on non-stored fields?
    # ====================================================================
    logger.section("STEP 2 — non-stored field searchability probes")
    probes = {}
    probes["payment_state_posted_searchcount"] = safe(
        "pay state", c.search_count, "account.payment", [("state", "=", "posted")])
    probes["payment_company1_searchcount"] = safe(
        "pay company", c.search_count, "account.payment", [("company_id", "=", 1)])
    probes["payment_journal_in_realbank_searchcount"] = safe(
        "pay journal", c.search_count, "account.payment",
        [("journal_id", "in", real_ids)]) if real_ids else None
    probes["payment_order_by_date_works"] = safe(
        "pay order date", c.search_read, "account.payment",
        [("state", "=", "posted")], ["id", "date"], 1, 0, "date asc")
    probes["stmtline_journal_in_realbank_searchcount"] = safe(
        "stmt journal", c.search_count, "account.bank.statement.line",
        [("journal_id", "in", real_ids)]) if real_ids else None
    probes["stmtline_order_by_date_works"] = safe(
        "stmt order date", c.search_read, "account.bank.statement.line",
        [("journal_id", "in", real_ids)] if real_ids else [], ["id", "date"], 1, 0, "date asc")
    rep["searchability_probes"] = probes

    # ====================================================================
    # STEP 3 — UNIVERSE (a): account.bank.statement.line on bank journals
    # ====================================================================
    logger.section("STEP 3 — statement lines on REAL bank journals")
    sl = {}
    sl["total_all_lines"] = safe("sl all", c.search_count,
                                 "account.bank.statement.line", [])
    sl["bank_journal_lines_total"] = safe(
        "sl bank", c.search_count, "account.bank.statement.line",
        [("journal_id", "in", real_ids)]) if real_ids else 0
    sl["bank_journal_lines_unrecon"] = safe(
        "sl bank unrecon", c.search_count, "account.bank.statement.line",
        [("journal_id", "in", real_ids), ("is_reconciled", "=", False)]) if real_ids else 0
    sl["visa_journal_lines_total"] = safe(
        "sl visa", c.search_count, "account.bank.statement.line",
        [("journal_id", "in", visa_ids)]) if visa_ids else 0
    # per real-bank-journal split
    per_j = []
    for r in real_bank:
        jid = r["id"]
        tot = safe("slj", c.search_count, "account.bank.statement.line",
                   [("journal_id", "=", jid)])
        unr = safe("slju", c.search_count, "account.bank.statement.line",
                   [("journal_id", "=", jid), ("is_reconciled", "=", False)])
        if (isinstance(tot, int) and tot) or (isinstance(unr, int) and unr):
            per_j.append({"journal": f"{r['code']} {r['name']}", "company_id": r["company_id"],
                          "total": tot, "unreconciled": unr})
    sl["per_real_bank_journal"] = per_j
    # cash-journal open gap (context, Area-1 overlap)
    cash_ids = safe("cash ids", c.search, "account.journal", [("type", "=", "cash")], 500)
    if isinstance(cash_ids, list) and cash_ids:
        sl["cash_journal_lines_total"] = safe(
            "cash sl", c.search_count, "account.bank.statement.line",
            [("journal_id", "in", cash_ids)])
        sl["cash_journal_lines_unrecon"] = safe(
            "cash sl unrecon", c.search_count, "account.bank.statement.line",
            [("journal_id", "in", cash_ids), ("is_reconciled", "=", False)])
    rep["statement_lines"] = sl

    # ====================================================================
    # STEP 4 — UNIVERSE (b): account.payment health
    # ====================================================================
    logger.section("STEP 4 — account.payment by state / flag / company / direction")
    pay = {}
    pay["total"] = safe("pay total", c.search_count, "account.payment", [])
    # by state
    pay["by_state"] = {s: safe(f"pay {s}", c.search_count, "account.payment",
                               [("state", "=", s)])
                       for s in ("draft", "posted", "cancel")}
    POSTED = [("state", "=", "posted")]
    pay["posted_total"] = safe("posted", c.search_count, "account.payment", POSTED)
    pay["posted_is_reconciled_false"] = safe(
        "posted unrecon", c.search_count, "account.payment",
        POSTED + [("is_reconciled", "=", False)])
    pay["posted_is_matched_false"] = safe(
        "posted unmatched", c.search_count, "account.payment",
        POSTED + [("is_matched", "=", False)])
    pay["posted_recon_false_AND_matched_false"] = safe(
        "posted both", c.search_count, "account.payment",
        POSTED + [("is_reconciled", "=", False), ("is_matched", "=", False)])
    # direction
    pay["posted_by_direction"] = {
        d: safe(f"dir {d}", c.search_count, "account.payment",
                POSTED + [("payment_type", "=", d)])
        for d in ("inbound", "outbound")}
    pay["posted_unrecon_by_direction"] = {
        d: safe(f"undir {d}", c.search_count, "account.payment",
                POSTED + [("is_reconciled", "=", False), ("payment_type", "=", d)])
        for d in ("inbound", "outbound")}
    # per company (loop — company_id non-stored, search delegated)
    per_co = {}
    for cid, cname in COMPANIES.items():
        co = [("company_id", "=", cid)]
        per_co[str(cid)] = {
            "name": cname,
            "posted": safe("c posted", c.search_count, "account.payment", POSTED + co),
            "posted_unrecon": safe("c unrecon", c.search_count, "account.payment",
                                   POSTED + co + [("is_reconciled", "=", False)]),
            "posted_unmatched": safe("c unmatched", c.search_count, "account.payment",
                                     POSTED + co + [("is_matched", "=", False)]),
            "posted_unrecon_amount": sum_amount(
                c, "account.payment",
                POSTED + co + [("is_reconciled", "=", False)]),
        }
    pay["per_company"] = per_co
    # which bank journals do unreconciled payments sit on? (loop real bank journals)
    pj = []
    for r in real_bank:
        n = safe("pj", c.search_count, "account.payment",
                 POSTED + [("is_reconciled", "=", False), ("journal_id", "=", r["id"])])
        if isinstance(n, int) and n:
            pj.append({"journal": f"{r['code']} {r['name']}", "company_id": r["company_id"],
                       "posted_unrecon": n})
    pay["posted_unrecon_per_real_bank_journal"] = sorted(
        pj, key=lambda x: -(x["posted_unrecon"] or 0))
    # oldest unreconciled posted payment (test ordering)
    pay["oldest_posted_unrecon"] = safe(
        "oldest", c.search_read, "account.payment",
        POSTED + [("is_reconciled", "=", False)],
        ["id", "date", "payment_type", "amount", "company_id", "journal_id"],
        1, 0, "date asc")
    pay["total_posted_unrecon_amount"] = sum_amount(
        c, "account.payment", POSTED + [("is_reconciled", "=", False)])
    rep["payments"] = pay

    # ====================================================================
    # STEP 5 — GAP: bank SUSPENSE account residual
    # ====================================================================
    logger.section("STEP 5 — bank suspense account residual")
    susp = {}
    # gather suspense account ids: from journals + by code/name search
    susp_search = safe("susp accts", c.search_read, "account.account",
                       ["|", ("code", "=", "201001"), ("name", "ilike", "suspense")],
                       ["id", "code", "name", "account_type", "reconcile", "company_id"], 50)
    susp_ids = sorted(set(susp_ids_from_jrn) |
                      {a["id"] for a in susp_search if isinstance(susp_search, list)})
    susp["suspense_accounts"] = susp_search
    susp["suspense_account_ids"] = susp_ids
    susp["suspense_ids_from_journals"] = susp_ids_from_jrn
    if susp_ids:
        base = [("account_id", "in", susp_ids), ("parent_state", "=", "posted")]
        susp["aml_total_posted"] = safe("susp aml", c.search_count,
                                        "account.move.line", base)
        susp["aml_nonzero_residual"] = sum_amount(
            c, "account.move.line",
            base + [("amount_residual", "!=", 0)], field="amount_residual")
        susp["aml_not_reconciled"] = safe(
            "susp unrec", c.search_count, "account.move.line",
            base + [("reconciled", "=", False)])
        susp["aml_balance_sum"] = sum_amount(c, "account.move.line", base, field="balance")
        # per company (AML.company_id IS stored -> read_group ok)
        susp["residual_by_company"] = safe(
            "susp by co", rg, c, "account.move.line",
            base + [("amount_residual", "!=", 0)],
            ["amount_residual:sum", "balance:sum"], ["company_id"])
        # oldest non-zero residual line
        susp["oldest_nonzero_residual"] = safe(
            "susp oldest", c.search_read, "account.move.line",
            base + [("amount_residual", "!=", 0)],
            ["id", "date", "account_id", "balance", "amount_residual", "company_id",
             "journal_id", "name"], 3, 0, "date asc")
    rep["suspense"] = susp

    # ====================================================================
    # STEP 6 — GAP: DRAFT bank journal entries (account.move, stored fields)
    # ====================================================================
    logger.section("STEP 6 — draft bank journal entries")
    drafts = {}
    if real_ids:
        drafts["draft_moves_total"] = safe(
            "draft", c.search_count, "account.move",
            [("journal_id", "in", real_ids), ("state", "=", "draft")])
        drafts["posted_moves_total"] = safe(
            "posted mv", c.search_count, "account.move",
            [("journal_id", "in", real_ids), ("state", "=", "posted")])
        drafts["draft_by_journal"] = safe(
            "draft by jrn", rg, c, "account.move",
            [("journal_id", "in", real_ids), ("state", "=", "draft")],
            ["amount_total:sum"], ["journal_id"])
        drafts["draft_by_company"] = safe(
            "draft by co", rg, c, "account.move",
            [("journal_id", "in", real_ids), ("state", "=", "draft")],
            ["amount_total:sum"], ["company_id"])
        drafts["oldest_draft"] = safe(
            "oldest draft", c.search_read, "account.move",
            [("journal_id", "in", real_ids), ("state", "=", "draft")],
            ["id", "name", "date", "amount_total", "company_id", "journal_id"],
            3, 0, "date asc")
    rep["draft_bank_moves"] = drafts

    # ====================================================================
    # DUMP + SUMMARY
    # ====================================================================
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    logger.success(f"Raw dump -> {OUT}")

    print("\n" + "=" * 78)
    print("AREA 3 — BANK MOVEMENTS & GAPS — SUMMARY")
    print("=" * 78)
    print(f"\nBank-type journals: {len(jrns)}  =>  REAL bank: {len(real_bank)} | "
          f"Visa-holding: {len(visa_hold)} | cash journals: {rep['cash_journal_count']}")
    print("\nREAL bank journals per company:")
    for cid, lst in rep["real_bank_journals_per_company"].items():
        nm = COMPANIES.get(int(cid)) if cid not in ("None", None) else cid
        print(f"  co{cid} {nm}: {len(lst)}")
        for s in lst:
            print(f"      - {s}")

    print("\n--- searchability probes (non-stored fields) ---")
    for k, v in probes.items():
        print(f"  {k}: {v}")

    print("\n--- (a) statement lines ---")
    print(f"  all lines: {sl.get('total_all_lines')}")
    print(f"  REAL bank journals: total={sl.get('bank_journal_lines_total')} "
          f"unrecon={sl.get('bank_journal_lines_unrecon')}")
    print(f"  Visa journals lines: {sl.get('visa_journal_lines_total')}")
    print(f"  CASH journals: total={sl.get('cash_journal_lines_total')} "
          f"unrecon={sl.get('cash_journal_lines_unrecon')}")
    for row in sl.get("per_real_bank_journal", []):
        print(f"      {row['journal']}: total={row['total']} unrecon={row['unreconciled']}")

    print("\n--- (b) account.payment ---")
    print(f"  total={pay.get('total')} by_state={pay.get('by_state')}")
    print(f"  posted={pay.get('posted_total')} "
          f"unrecon={pay.get('posted_is_reconciled_false')} "
          f"unmatched={pay.get('posted_is_matched_false')} "
          f"both={pay.get('posted_recon_false_AND_matched_false')}")
    print(f"  direction posted={pay.get('posted_by_direction')}")
    print(f"  direction posted-unrecon={pay.get('posted_unrecon_by_direction')}")
    print(f"  total posted-unrecon amount={pay.get('total_posted_unrecon_amount')}")
    print("  per company:")
    for cid, d in pay.get("per_company", {}).items():
        print(f"      co{cid} {d['name']}: posted={d['posted']} "
              f"unrecon={d['posted_unrecon']} unmatched={d['posted_unmatched']} "
              f"unrecon_amt={d['posted_unrecon_amount']}")
    print(f"  oldest posted-unrecon: {pay.get('oldest_posted_unrecon')}")
    print("  posted-unrecon per REAL bank journal:")
    for row in pay.get("posted_unrecon_per_real_bank_journal", [])[:15]:
        print(f"      {row['journal']}: {row['posted_unrecon']}")

    print("\n--- suspense ---")
    print(f"  accounts: {[(a['code'], a['name'], a['account_type'], a['reconcile']) for a in (susp.get('suspense_accounts') or []) if isinstance(a, dict)]}")
    print(f"  ids: {susp.get('suspense_account_ids')}")
    print(f"  aml posted total={susp.get('aml_total_posted')} "
          f"not_reconciled={susp.get('aml_not_reconciled')}")
    print(f"  nonzero residual: {susp.get('aml_nonzero_residual')}")
    print(f"  balance sum: {susp.get('aml_balance_sum')}")
    print(f"  residual by company: {susp.get('residual_by_company')}")
    print(f"  oldest nonzero residual: {susp.get('oldest_nonzero_residual')}")

    print("\n--- draft bank moves ---")
    print(f"  draft={drafts.get('draft_moves_total')} posted={drafts.get('posted_moves_total')}")
    print(f"  draft by company: {drafts.get('draft_by_company')}")
    print(f"  oldest draft: {drafts.get('oldest_draft')}")
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
