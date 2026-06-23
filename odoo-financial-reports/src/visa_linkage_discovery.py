"""
Area-2 FINAL discovery (READ-ONLY) — Session -> Geidea linkage & the "late" rule,
scoped to company #بالميه#. (company_id = 3) ONLY.

Builds on visa_confirm_discovery.py / visa_confirm_trace2.py. Established already:
  - confirmation signal = a JE crediting the Visa holding acct (17495/16823),
    counterpart 63001 Liquidity Transfer, ref ~"جيديا"/transfer;
  - holding accounts are reconcile=False -> NO line reconciliation;
  - branch = account.move.line.journal_id (co3 funnels VIS01..VIS07 into 17495).

This script answers, for company 3 only:
  1) LINKAGE granularity: is the Geidea confirmation posted per-session,
     per-branch-day, or as a periodic lump per branch? (pull ~12 recent
     confirmation credit moves; dissect counterparts 63001/31030; count debits.)
     + debit side: how a session's stop_at relates to the date its Visa debits
     the holding account (via account.payment.pos_session_id).
  2) 2-WORKING-DAY / Friday-only due-date math on REAL stop_at dates (worked
     examples incl. one crossing a Friday); within-window vs past-due branches.
  3) company-3 scoping + per-branch (journal) net pending (debit - credit).

READ-ONLY: search_read / read_group / read / search_count, small limits, always
filtered to the tiny company-3 holding-account id set. Never an unbounded AML scan.

Run:  PYTHONIOENCODING=utf-8 python -m src.visa_linkage_discovery
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from src.odoo_client import OdooReadOnlyClient
from src.utils import logger

OUT = Path("output") / "visa_linkage_discovery_raw.json"

CO3 = 3                      # company #بالميه#.
HOLDING_CO3 = [17495, 16823]  # the two active company-3 Visa holding accounts

AML = ["id", "account_id", "name", "debit", "credit", "balance", "amount_residual",
       "reconciled", "matching_number", "payment_id", "move_id", "date",
       "parent_state", "journal_id", "company_id"]


def safe(label, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{label} failed: {exc}")
        return {"__error__": str(exc)}


def rg(c, model, domain, fields, groupby, **kw):
    kw.setdefault("lazy", False)
    return c.execute_kw(model, "read_group", [domain, fields, groupby], kw)


def parse_d(s):
    """Odoo date/datetime string -> datetime.date."""
    if not s:
        return None
    s = str(s)
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def add_working_days(d: date, n: int) -> date:
    """Add n working days to d. Friday (weekday()==4) is the ONLY weekend day;
    Saturday is a working day. Counting starts the day AFTER d."""
    cur, added = d, 0
    while added < n:
        cur += timedelta(days=1)
        if cur.weekday() != 4:   # skip Fridays only
            added += 1
    return cur


def working_days_between(a: date, b: date) -> int:
    """# of working days from a (exclusive) to b (inclusive), Friday excluded."""
    if not a or not b or b <= a:
        return 0
    cur, n = a, 0
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() != 4:
            n += 1
    return n


WD = ["Mon", "Tue", "Wed", "Thu", "Fri(weekend)", "Sat", "Sun"]


def main():
    rep = {"generated_at": datetime.now().isoformat()}
    c = OdooReadOnlyClient()
    srv_dt = c.version_info.get("server_datetime")
    today = parse_d(srv_dt) or date.today()
    rep["connection"] = {"db": c.db, "uid": c.uid, "server_datetime": srv_dt,
                         "today_used": str(today)}
    logger.success(f"Connected uid={c.uid} db={c.db} | today={today} (srv={srv_dt})")

    # ====================================================================
    # STEP 1 — company-3 Visa methods -> journals -> holding accounts
    # ====================================================================
    logger.section("STEP 1 — co3 Visa methods / journals / holding accounts")
    vms = safe("co3 visa methods", c.search_read, "pos.payment.method",
               [("is_cash_count", "=", False), ("name", "like", "فيزا"),
                ("company_id", "=", CO3)],
               ["id", "name", "journal_id", "outstanding_account_id", "company_id"],
               200, 0, "id")
    rep["co3_visa_methods"] = vms
    method_journal_ids = sorted({m["journal_id"][0] for m in vms
                                 if isinstance(vms, list) and m.get("journal_id")})
    method_holding_ids = sorted({m["outstanding_account_id"][0] for m in vms
                                 if isinstance(vms, list) and m.get("outstanding_account_id")})
    rep["co3_method_journal_ids"] = method_journal_ids
    rep["co3_method_holding_ids"] = method_holding_ids

    # holding account meta
    rep["holding_accounts"] = safe("holding meta", c.search_read, "account.account",
                                   [("id", "in", HOLDING_CO3)],
                                   ["id", "code", "name", "account_type", "reconcile",
                                    "company_id"], 10)

    # counterpart accounts: 63001 Liquidity Transfer, 31030 commission
    rep["counterpart_accounts"] = safe(
        "counterpart accts", c.search_read, "account.account",
        ["|", ("code", "in", ["63001", "31030"]),
         ("name", "ilike", "Liquidity Transfer")],
        ["id", "code", "name", "account_type", "reconcile", "company_id"], 30)
    acct_63001 = [a["id"] for a in rep["counterpart_accounts"]
                  if isinstance(rep["counterpart_accounts"], list)
                  and (a.get("code") == "63001" or "Liquidity" in (a.get("name") or ""))]
    acct_31030 = [a["id"] for a in rep["counterpart_accounts"]
                  if isinstance(rep["counterpart_accounts"], list) and a.get("code") == "31030"]
    rep["acct_63001_ids"] = acct_63001
    rep["acct_31030_ids"] = acct_31030

    # journals that actually touch the holding accounts (the branch set)
    base = [("account_id", "in", HOLDING_CO3), ("parent_state", "=", "posted"),
            ("company_id", "=", CO3)]
    jrn_dbg = safe("debit by journal", rg, c, "account.move.line",
                   base + [("debit", ">", 0)], ["debit"], ["journal_id"])
    jrn_crg = safe("credit by journal", rg, c, "account.move.line",
                   base + [("credit", ">", 0)], ["credit"], ["journal_id"])
    rep["debit_by_journal"] = jrn_dbg
    rep["credit_by_journal"] = jrn_crg

    # ====================================================================
    # STEP 2 — LINKAGE: dissect ~12 recent CONFIRMATION (credit) moves
    # ====================================================================
    logger.section("STEP 2 — confirmation (credit) moves dissected")
    cr_lines = safe("recent credit holding lines", c.search_read, "account.move.line",
                    base + [("credit", ">", 0)], AML, 30, 0, "date desc, id desc")
    rep["recent_credit_lines"] = cr_lines

    move_ids = []
    if isinstance(cr_lines, list):
        for l in cr_lines:
            if l.get("move_id") and l["move_id"][0] not in move_ids:
                move_ids.append(l["move_id"][0])
    move_ids = move_ids[:12]

    confirm_moves = []
    for mid in move_ids:
        head = safe(f"move {mid}", c.search_read, "account.move",
                    [("id", "=", mid)], ["id", "name", "ref", "date", "journal_id",
                                         "move_type", "state", "company_id"], 1)
        head = head[0] if isinstance(head, list) and head else {}
        mlines = safe(f"move lines {mid}", c.search_read, "account.move.line",
                      [("move_id", "=", mid)],
                      ["id", "account_id", "name", "debit", "credit", "journal_id"], 60, 0, "id")
        # classify
        holding_credit = sum(l["credit"] for l in mlines
                             if isinstance(l, dict) and l.get("account_id")
                             and l["account_id"][0] in HOLDING_CO3) if isinstance(mlines, list) else 0
        holding_credit_lines = [l for l in mlines if isinstance(l, dict) and l.get("account_id")
                                and l["account_id"][0] in HOLDING_CO3 and l.get("credit")] if isinstance(mlines, list) else []
        has_63001 = any(l.get("account_id") and l["account_id"][0] in acct_63001
                        for l in mlines) if isinstance(mlines, list) else False
        has_31030 = any(l.get("account_id") and l["account_id"][0] in acct_31030
                        for l in mlines) if isinstance(mlines, list) else False
        counterpart_accts = sorted({tuple(l["account_id"]) for l in mlines
                                    if isinstance(l, dict) and l.get("account_id")
                                    and l["account_id"][0] not in HOLDING_CO3}) if isinstance(mlines, list) else []
        confirm_moves.append({
            "move": head,
            "holding_credit_total": round(holding_credit, 2),
            "n_holding_credit_lines": len(holding_credit_lines),
            "has_63001_leg": has_63001,
            "has_31030_commission_leg": has_31030,
            "counterpart_accounts": [list(t) for t in counterpart_accts],
            "lines": mlines,
        })
    rep["confirmation_moves"] = confirm_moves

    # ====================================================================
    # STEP 3 — DEBIT side: stop_at vs the date the Visa debits the holding
    # ====================================================================
    logger.section("STEP 3 — debit (collection) lines vs session stop_at")
    db_lines = safe("recent debit holding lines", c.search_read, "account.move.line",
                    base + [("debit", ">", 0)], AML, 20, 0, "date desc, id desc")
    rep["recent_debit_lines"] = db_lines

    pay_ids = [l["payment_id"][0] for l in db_lines
               if isinstance(db_lines, list) and isinstance(l, dict) and l.get("payment_id")]
    payments = safe("debit payments", c.search_read, "account.payment",
                    [("id", "in", pay_ids)],
                    ["id", "name", "amount", "journal_id", "pos_session_id", "date",
                     "pos_payment_method_id"], 60) if pay_ids else []
    pay_by_id = {p["id"]: p for p in payments} if isinstance(payments, list) else {}
    sess_ids = [p["pos_session_id"][0] for p in payments
                if isinstance(payments, list) and p.get("pos_session_id")]
    sessions = safe("debit sessions", c.search_read, "pos.session",
                    [("id", "in", sess_ids)],
                    ["id", "name", "state", "config_id", "start_at", "stop_at"], 60) if sess_ids else []
    sess_by_id = {s["id"]: s for s in sessions} if isinstance(sessions, list) else {}

    debit_trace = []
    if isinstance(db_lines, list):
        for l in db_lines:
            p = pay_by_id.get(l["payment_id"][0]) if l.get("payment_id") else None
            s = sess_by_id.get(p["pos_session_id"][0]) if p and p.get("pos_session_id") else None
            debit_trace.append({
                "line_id": l["id"], "line_date": l.get("date"),
                "journal": l.get("journal_id"), "debit": l.get("debit"),
                "name": l.get("name"),
                "payment": p["name"] if p else None,
                "session": s["name"] if s else None,
                "session_state": s["state"] if s else None,
                "stop_at": s.get("stop_at") if s else None,
                "config": s.get("config_id") if s else None,
            })
    rep["debit_trace"] = debit_trace

    # ====================================================================
    # STEP 4 — per branch (journal) per day: collected vs confirmed
    # ====================================================================
    logger.section("STEP 4 — per-branch/day collected vs confirmed")
    db_by_jd = safe("debit by journal/day", rg, c, "account.move.line",
                    base + [("debit", ">", 0)], ["debit"], ["journal_id", "date:day"])
    cr_by_jd = safe("credit by journal/day", rg, c, "account.move.line",
                    base + [("credit", ">", 0)], ["credit"], ["journal_id", "date:day"])
    rep["debit_by_journal_day"] = db_by_jd
    rep["credit_by_journal_day"] = cr_by_jd

    # ====================================================================
    # STEP 5 — per-branch NET pending + last collection/confirmation dates
    # ====================================================================
    logger.section("STEP 5 — per-branch net pending")
    net_by_journal = safe("net by journal", rg, c, "account.move.line",
                          base, ["debit", "credit", "balance"], ["journal_id"])
    rep["net_by_journal"] = net_by_journal

    # last credit (confirmation) date per journal — from a recent credit pull
    last_credit_date = {}
    if isinstance(cr_lines, list):
        for l in cr_lines:
            jid = l["journal_id"][0] if l.get("journal_id") else None
            d = l.get("date")
            if jid and d and (jid not in last_credit_date or d > last_credit_date[jid]):
                last_credit_date[jid] = d
    # last debit (collection) date per journal
    last_debit_date = {}
    recent_db_all = safe("recent debits all", c.search_read, "account.move.line",
                         base + [("debit", ">", 0)],
                         ["journal_id", "date"], 80, 0, "date desc, id desc")
    if isinstance(recent_db_all, list):
        for l in recent_db_all:
            jid = l["journal_id"][0] if l.get("journal_id") else None
            d = l.get("date")
            if jid and d and (jid not in last_debit_date or d > last_debit_date[jid]):
                last_debit_date[jid] = d
    rep["last_credit_date_by_journal"] = last_credit_date
    rep["last_debit_date_by_journal"] = last_debit_date

    # ====================================================================
    # STEP 6 — 2-working-day due-date math on REAL closed sessions (co3)
    # ====================================================================
    logger.section("STEP 6 — 2-working-day due dates on real stop_at")
    vm_ids = [m["id"] for m in vms] if isinstance(vms, list) else []
    # recent CLOSED sessions in co3 that had Visa payments
    rvp = safe("recent co3 visa payments", c.search_read, "pos.payment",
               [("payment_method_id", "in", vm_ids), ("amount", ">", 0)],
               ["id", "amount", "session_id", "payment_date"], 120, 0, "id desc")
    cand_sids = []
    if isinstance(rvp, list):
        for p in rvp:
            sid = p.get("session_id")
            if sid and sid[0] not in cand_sids:
                cand_sids.append(sid[0])
    closed = safe("recent closed co3 sessions", c.search_read, "pos.session",
                  [("id", "in", cand_sids), ("state", "=", "closed")],
                  ["id", "name", "config_id", "stop_at", "start_at"], 40, 0, "stop_at desc")
    worked = []
    if isinstance(closed, list):
        for s in closed[:12]:
            sd = parse_d(s.get("stop_at"))
            if not sd:
                continue
            due = add_working_days(sd, 2)
            crosses_fri = any((sd + timedelta(days=i)).weekday() == 4 for i in range(1, (due - sd).days + 1))
            overdue_wd = working_days_between(sd, today)
            worked.append({
                "session": s["name"], "config": s.get("config_id"),
                "stop_at": s.get("stop_at"),
                "stop_weekday": WD[sd.weekday()],
                "due_date": str(due), "due_weekday": WD[due.weekday()],
                "calendar_days_added": (due - sd).days,
                "crosses_friday": crosses_fri,
                "working_days_since_close_to_today": overdue_wd,
                "past_due_as_of_today": overdue_wd > 2,
            })
    rep["due_date_examples"] = worked

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    logger.success(f"written {OUT}")

    # ================= CONSOLE =================
    def jname(jt):
        return f"{jt[1]}" if jt else "?"

    print("\n================ AREA-2 LINKAGE DISCOVERY (company #بالميه#. / co3) ================")
    print(f"server today = {today}  (server_datetime={srv_dt})")
    print(f"holding accounts: {HOLDING_CO3}")
    for a in (rep["holding_accounts"] if isinstance(rep["holding_accounts"], list) else []):
        print(f"   acct {a['id']} code {a.get('code')} '{a.get('name')}' "
              f"type={a.get('account_type')} reconcile={a.get('reconcile')} co={a.get('company_id')}")
    print(f"63001 ids={acct_63001}  31030 ids={acct_31030}")

    print("\n-- co3 Visa methods (branch -> journal -> holding):")
    for m in (vms if isinstance(vms, list) else []):
        print(f"   m{m['id']:>4} '{m.get('name')}' journal={jname(m.get('journal_id'))} "
              f"holding={m.get('outstanding_account_id')}")

    print("\n-- journals touching holding (DEBIT side = branches collecting):")
    for g in (jrn_dbg if isinstance(jrn_dbg, list) else []):
        print(f"   {jname(g.get('journal_id')):<40} count {g.get('__count'):>5}  DR {g.get('debit'):>14,.2f}")
    print("-- journals touching holding (CREDIT side = confirmations):")
    for g in (jrn_crg if isinstance(jrn_crg, list) else []):
        print(f"   {jname(g.get('journal_id')):<40} count {g.get('__count'):>5}  CR {g.get('credit'):>14,.2f}")

    print("\n-- 12 RECENT CONFIRMATION (credit) MOVES dissected:")
    for cm in confirm_moves:
        mv = cm["move"]
        print(f"   {mv.get('name'):<18} {mv.get('date')} jrn={jname(mv.get('journal_id'))}")
        print(f"       ref='{mv.get('ref')}' | holding CR total={cm['holding_credit_total']:,.2f} "
              f"in {cm['n_holding_credit_lines']} line(s) | 63001={cm['has_63001_leg']} "
              f"31030comm={cm['has_31030_commission_leg']}")
        for l in cm["lines"]:
            if isinstance(l, dict):
                tag = "HOLD" if (l.get("account_id") and l["account_id"][0] in HOLDING_CO3) else "    "
                print(f"        {tag} acct {l.get('account_id')} D {l.get('debit'):>12,.2f} C {l.get('credit'):>12,.2f}  '{l.get('name')}'")

    print("\n-- DEBIT (collection) lines vs session stop_at:")
    for t in debit_trace[:14]:
        print(f"   line {t['line_id']} date={t['line_date']} jrn={jname(t['journal'])} DR {t['debit']:,.2f}")
        print(f"       pay={t['payment']} sess={t['session']} state={t['session_state']} "
              f"stop_at={t['stop_at']} config={jname(t['config'])}")

    print("\n-- per-branch NET pending (DR - CR), last collect / last confirm:")
    for g in (net_by_journal if isinstance(net_by_journal, list) else []):
        jt = g.get("journal_id")
        jid = jt[0] if jt else None
        net = (g.get("debit") or 0) - (g.get("credit") or 0)
        lc = last_credit_date.get(jid)
        ld = last_debit_date.get(jid)
        flag = ""
        if net > 0.5 and lc:
            wd_since_conf = working_days_between(parse_d(lc), today)
            flag = f"  [last confirm {lc}, {wd_since_conf} wd ago{' >>> LATE' if wd_since_conf > 2 else ''}]"
        elif net > 0.5 and not lc:
            flag = "  [NO confirmation credit seen]"
        print(f"   {jname(jt):<40} DR {g.get('debit'):>14,.2f} CR {g.get('credit'):>14,.2f} "
              f"NET {net:>14,.2f} | lastDR {ld}{flag}")

    print("\n-- 2-WORKING-DAY due-date examples (Friday = only weekend):")
    for w in worked:
        print(f"   {w['session']:<14} stop_at {w['stop_at']} ({w['stop_weekday']}) "
              f"-> due {w['due_date']} ({w['due_weekday']}) "
              f"[+{w['calendar_days_added']}cal, crossesFri={w['crosses_friday']}] "
              f"| {w['working_days_since_close_to_today']}wd since close"
              f"{'  PAST DUE' if w['past_due_as_of_today'] else '  within window'}")
    print("====================================================================================\n")


if __name__ == "__main__":
    main()
