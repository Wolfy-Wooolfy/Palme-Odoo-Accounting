"""Bank Movements & Gaps — ALL bank movements per bank account, gaps highlighted (Area 3).

Answers the user's question: *"see ALL bank movements and whether there are GAPS or
everything is reconciled — everything is supposed to be recorded."* (see
DISCOVERY_REPORT.md → "Area 3 — Bank Movements & Gap Mechanics"). The true bank
**statement lines are 100% clean** (gap = 0); the real exposure is **unreconciled
``account.payment`` (~419M EGP)** plus **bank-suspense net balance (~18M EGP)**.

100% READ-ONLY. Uses only ``search_read`` / ``search_count`` / ``read`` / ``read_group``
/ ``fields_get`` on the shared OdooReadOnlyClient (the client hard-blocks every write
method and serialises RPC dispatch internally, so the shared singleton is safe).

This screen = **27 REAL bank/treasury journals** + the bank-side ``account.payment``
universe + the **bank-suspense** accounts. It deliberately EXCLUDES the ~56 Visa-holding
journals (Area 2 card settlements) and the open cash-drawer statement lines (Area 1 POS
drawers) — neither is touched here, so nothing is double-counted.

Key discovery facts baked in (verified live 2026-06-24; do not rediscover):
* BANK JOURNALS: ``account.journal type='bank'`` = 83 → 27 REAL bank/treasury, 56
  Visa-holding. Visa-holding ⇔ ``code`` starts 'VIS' OR name/default-account name
  contains 'فيزا'/'visa', AND no ``bank_account_id``. Classified generically (no ids
  hardcoded). 3 of the 27 are not clearing banks — FX treasury (خزينة دولار) /
  notes-receivable (اوراق قبض) — kept but tagged so they're attributed correctly.
* MOVEMENTS UNIVERSE = ``account.payment`` (statements are unused: 0 bank statements,
  and the 920 real-bank statement lines are all reconciled). On ``account.payment``,
  ``journal_id``/``company_id``/``state``/``date`` are store=False BUT domain-filter,
  order-by and read_group ALL work (delegated to ``account.move``) — verified.
* GAP flag = posted ∧ ``is_reconciled = False`` (``is_matched`` is unreliable here
  because statements are unused — shown as a secondary column only). Baseline ≈ 3,006
  unreconciled posted payments ≈ 419M EGP (co1 741/70.7M, co2 1,058/213M, co3 1,207/135.6M;
  oldest 2024-06-01).
* SUSPENSE GAP (separate panel): bank-suspense accounts (101402 co1/co2, 201001 co3,
  110160) are ``reconcile=False`` → ``amount_residual`` is always 0, so the gap is sized
  by NET ``balance`` on ``account.move.line`` (parent_state='posted'). Baseline ≈ 18.0M net
  (≈17.79M in co1 101402). Same gotcha as the Area-2 holding accounts.

Time semantics: GAP totals are full-history "as of today" (a backlog can be months old);
MOVEMENT VOLUME is windowed by the date filter. Each returned block states which it uses.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from api.models.bank import BankGapDetailFilter, BankMovementsFilter

# ── Classification anchors (generic — nothing hardcoded to specific journal ids) ──
VISA_CODE_PREFIX = "VIS"
VISA_NAME_TOKENS = ("فيزا", "visa")

# Bank-suspense accounts: reconcile=False clearing accounts sized by NET balance.
SUSPENSE_NAME_TOKEN = "suspense"
SUSPENSE_CODES = ("101402", "201001", "110160")

# Non-clearing real-bank journals (kept, but tagged so the UI can attribute correctly).
FX_TREASURY_TOKENS = ("دولار", "$", "usd")   # خزينة دولار / بنك اسكندرية $
NOTES_TOKENS = ("اوراق قبض", "أوراق قبض", "notes receivable")

# Optional account.payment fields probed once via fields_get (names differ across builds).
_CANDIDATE_PAYMENT_REF_FIELDS = ("ref", "memo", "communication")
_payment_field_cache: set | None = None

_DEFAULT_MOVEMENT_DAYS = 90


# ── Pure plumbing helpers (no Odoo) ───────────────────────────────────────────────

def _m2o(value) -> tuple:
    """Split an Odoo many2one ``[id, name]`` pair into ``(id, name)``."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    return None, ""


def _parse_date(value) -> date | None:
    """Parse a stored Odoo date ('YYYY-MM-DD'). Tolerates a full datetime string."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_all(client, model, domain, fields, *, order=None, batch=2000, hard_cap=40000):
    """Paginated search_read — BOUNDED by the caller's domain (never an open scan).

    The client default limit is 80, so page explicitly. ``hard_cap`` is a runaway
    backstop; the bounded domains here (bank-journal gaps ~1k, suspense lines ~1.8k)
    never approach it.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        page = client.search_read(model, domain=domain, fields=fields,
                                  limit=batch, offset=offset, order=order)
        rows.extend(page)
        if len(page) < batch or len(rows) >= hard_cap:
            break
        offset += batch
    return rows


def _read_group(client, model, domain, fields, groupby):
    """read_group with lazy=False (full multi-key grouping + ``__count`` per row)."""
    return client.execute_kw(model, "read_group", [domain, fields, groupby], {"lazy": False})


def _classify_kind(name: str, acct_name: str) -> str:
    """Tag a real-bank journal: clearing_bank | fx_treasury | notes (informational)."""
    blob = f"{name} {acct_name}".lower()
    if any(tok in blob for tok in NOTES_TOKENS):
        return "notes"
    if any(tok in blob for tok in FX_TREASURY_TOKENS):
        return "fx_treasury"
    return "clearing_bank"


# ── Odoo discovery helpers ────────────────────────────────────────────────────────

def _available_payment_ref_fields(client) -> set:
    """Which of the candidate reference fields actually exist on account.payment.

    Reading a non-existent field raises, so probe once with fields_get (a read method)
    and cache. Always includes the always-present fields the movements list needs.
    """
    global _payment_field_cache
    if _payment_field_cache is not None:
        return _payment_field_cache
    present: set = set()
    try:
        meta = client.execute_kw(
            "account.payment", "fields_get",
            [list(_CANDIDATE_PAYMENT_REF_FIELDS)], {"attributes": ["type"]},
        )
        present = {f for f in _CANDIDATE_PAYMENT_REF_FIELDS if f in (meta or {})}
    except Exception:
        present = set()
    _payment_field_cache = present
    return present


def _classify_bank_journals(client, company_id: int | None) -> dict:
    """Split ``type='bank'`` journals into REAL bank vs Visa-holding (Area 2).

    Returns ``{real: [...], real_ids: [...], visa_ids: [...], journal_suspense_ids: [...]}``.
    Each real-bank row: ``{journal_id, code, name, company_id, company, kind}``. Visa-holding
    ⇔ code starts 'VIS' OR name/default-account name contains 'فيزا'/'visa', AND no
    ``bank_account_id`` (the discovery's own rule). Scoped to ``company_id`` when given.
    """
    domain = [("type", "=", "bank")]
    if company_id:
        domain.append(("company_id", "=", company_id))
    journals = _fetch_all(
        client, "account.journal", domain,
        ["id", "code", "name", "company_id", "default_account_id",
         "bank_account_id", "suspense_account_id"],
        order="company_id, code",
    )

    def_ids = sorted({_m2o(j["default_account_id"])[0] for j in journals
                      if j.get("default_account_id")})
    acct_name_by_id: dict = {}
    if def_ids:
        for a in client.read("account.account", def_ids, ["id", "name"]):
            acct_name_by_id[a["id"]] = a.get("name") or ""

    real: list[dict] = []
    visa_ids: list[int] = []
    journal_suspense_ids: set = set()
    for j in journals:
        code = (j.get("code") or "")
        name = (j.get("name") or "")
        acct_name = acct_name_by_id.get(_m2o(j.get("default_account_id"))[0], "")
        blob_name = f"{name} {acct_name}".lower()
        is_visa = (
            code.upper().startswith(VISA_CODE_PREFIX)
            or any(tok in name for tok in VISA_NAME_TOKENS if tok == "فيزا")
            or any(tok in blob_name for tok in VISA_NAME_TOKENS)
        )
        has_bank_acct = bool(j.get("bank_account_id"))
        susp = _m2o(j.get("suspense_account_id"))[0]
        if susp:
            journal_suspense_ids.add(susp)
        if is_visa and not has_bank_acct:
            visa_ids.append(j["id"])
            continue
        cid, cname = _m2o(j.get("company_id"))
        real.append({
            "journal_id": j["id"],
            "code": code,
            "name": name or code or "—",
            "company_id": cid,
            "company": cname,
            "kind": _classify_kind(name, acct_name),
        })
    return {
        "real": real,
        "real_ids": [r["journal_id"] for r in real],
        "visa_ids": visa_ids,
        "journal_suspense_ids": sorted(journal_suspense_ids),
    }


def _resolve_suspense_accounts(client, company_id: int | None, journal_suspense_ids: list[int]) -> dict:
    """Bank-suspense accounts (reconcile=False) for the company filter.

    Mirrors the discovery resolution: ``account.account`` where name contains 'suspense'
    OR code in the known suspense codes, UNION the ``suspense_account_id`` of the bank
    journals (already company-scoped via the journal fetch). Keeps only reconcile=False
    rows (suspense accounts are reconcile=False; this guards against pulling in a real
    account that merely shares a token). Returns ``{id: {code, name, company_id, company}}``.
    """
    inner = ["|", ("name", "ilike", SUSPENSE_NAME_TOKEN), ("code", "in", list(SUSPENSE_CODES))]
    domain = (["&", ("company_id", "=", company_id)] + inner) if company_id else inner
    by_id: dict = {}
    for r in client.search_read(
        "account.account", domain=domain,
        fields=["id", "code", "name", "company_id", "reconcile"], limit=200,
    ):
        by_id[r["id"]] = r
    extra = [i for i in journal_suspense_ids if i not in by_id]
    if extra:
        for r in client.read("account.account", extra,
                             ["id", "code", "name", "company_id", "reconcile"]):
            by_id[r["id"]] = r
    out: dict = {}
    for i, r in by_id.items():
        if r.get("reconcile"):
            continue  # reconcilable → not a suspense clearing account
        cid, cname = _m2o(r.get("company_id"))
        out[i] = {"code": r.get("code") or "", "name": r.get("name") or "—",
                  "company_id": cid, "company": cname}
    return out


# ── Aggregate helpers over account.payment ────────────────────────────────────────

def _direction_totals(client, base_domain) -> dict:
    """Count + amount split by ``payment_type`` (inbound/outbound) over a payment domain.

    Returns ``{count, amount, inbound_count, inbound_amount, outbound_count, outbound_amount}``.
    ``payment_type`` is a stored selection on account.payment, so this read_group is exact.
    """
    out = {"count": 0, "amount": 0.0,
           "inbound_count": 0, "inbound_amount": 0.0,
           "outbound_count": 0, "outbound_amount": 0.0}
    groups = _read_group(client, "account.payment", base_domain, ["amount:sum"], ["payment_type"])
    for g in groups:
        cnt = int(g.get("__count") or 0)
        amt = float(g.get("amount") or 0.0)
        out["count"] += cnt
        out["amount"] += amt
        if g.get("payment_type") == "inbound":
            out["inbound_count"] += cnt
            out["inbound_amount"] += amt
        elif g.get("payment_type") == "outbound":
            out["outbound_count"] += cnt
            out["outbound_amount"] += amt
    return out


def _company_domain(company_id: int | None) -> list:
    return [("company_id", "=", company_id)] if company_id else []


# ── Main entry point ──────────────────────────────────────────────────────────────

def _empty_summary(as_of: str) -> dict:
    return {
        "total_movements_count": 0, "total_inbound_amount": 0.0, "total_outbound_amount": 0.0,
        "gap_count": 0, "gap_amount": 0.0, "gap_inbound_amount": 0.0, "gap_outbound_amount": 0.0,
        "gap_count_on_bank_journals": 0, "gap_amount_on_bank_journals": 0.0,
        "suspense_net_balance": 0.0, "suspense_nonzero_lines": 0,
        "oldest_gap_date": None, "draft_bank_moves_count": 0, "as_of": as_of,
    }


def compute_bank_movements(client, filters: BankMovementsFilter) -> dict:
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    company_id = filters.company_id
    is_all_companies = company_id is None

    # Movement-volume window (the ONLY thing the date filter drives). Default = 90 days.
    date_to = filters.date_to or today
    date_from = filters.date_from or (date_to - timedelta(days=_DEFAULT_MOVEMENT_DAYS))
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    df, dt = date_from.isoformat(), date_to.isoformat()

    cls = _classify_bank_journals(client, company_id)
    real = cls["real"]
    real_ids = cls["real_ids"]
    jmeta = {r["journal_id"]: r for r in real}

    base_block = {
        "as_of": now_utc.isoformat(),
        "period": {"from": df, "to": dt},
        "company_id": company_id,
        "is_all_companies": is_all_companies,
        "gaps_only": filters.gaps_only,
        "statement_lines_note": "Bank statement lines are 100% reconciled (0 open) — the gap lives in account.payment + suspense.",
    }

    # A company with no real bank journals → graceful empty (HTTP 200).
    if not real_ids:
        return {
            **base_block,
            "summary": _empty_summary(now_utc.isoformat()),
            "by_bank": [], "movements": [], "movements_total_count": 0,
            "movements_offset": filters.offset, "movements_limit": filters.limit,
            "suspense": [], "draft_bank_moves": [],
        }

    co_dom = _company_domain(company_id)
    posted = [("state", "=", "posted")]

    # ── SUMMARY ───────────────────────────────────────────────────────────────────
    # GAP totals (full-history, ALL journals — the headline backlog the user asked about).
    gap_dom = posted + [("is_reconciled", "=", False)] + co_dom
    gap_tot = _direction_totals(client, gap_dom)
    # MOVEMENT volume (date-windowed, all posted payments in range).
    mv_dom = posted + [("date", ">=", df), ("date", "<=", dt)] + co_dom
    mv_tot = _direction_totals(client, mv_dom)
    # Oldest gap (oldest unreconciled posted payment), all journals.
    oldest_gap_row = client.search_read(
        "account.payment", domain=gap_dom, fields=["date"], order="date asc", limit=1)
    oldest_gap_date = _parse_date(oldest_gap_row[0]["date"]) if oldest_gap_row else None

    # ── BY BANK (REAL bank journals only — Visa excluded) ─────────────────────────
    # Movements per journal (date-windowed) + gaps per journal (full-history). Both via
    # read_group (bounded: <= 27*2 rows). Per-journal dates come from bounded row fetches.
    bank_mv_dom = posted + [("journal_id", "in", real_ids), ("date", ">=", df), ("date", "<=", dt)] + co_dom
    bank_mv = _read_group(client, "account.payment", bank_mv_dom, ["amount:sum"], ["journal_id", "payment_type"])
    bank_gap_dom = posted + [("is_reconciled", "=", False), ("journal_id", "in", real_ids)] + co_dom
    bank_gap = _read_group(client, "account.payment", bank_gap_dom, ["amount:sum"], ["journal_id"])

    rows: dict = {}
    for r in real:
        rows[r["journal_id"]] = {
            "journal_id": r["journal_id"], "bank": r["name"], "journal_code": r["code"],
            "company": r["company"], "company_id": r["company_id"], "kind": r["kind"],
            "inbound_count": 0, "inbound_amount": 0.0, "outbound_count": 0, "outbound_amount": 0.0,
            "movements_amount": 0.0, "gap_count": 0, "gap_amount": 0.0,
            "last_movement_date": None, "oldest_gap_date": None,
        }
    for g in bank_mv:
        jid = _m2o(g.get("journal_id"))[0]
        row = rows.get(jid)
        if row is None:
            continue
        cnt = int(g.get("__count") or 0)
        amt = float(g.get("amount") or 0.0)
        row["movements_amount"] += amt
        if g.get("payment_type") == "inbound":
            row["inbound_count"] += cnt
            row["inbound_amount"] += amt
        elif g.get("payment_type") == "outbound":
            row["outbound_count"] += cnt
            row["outbound_amount"] += amt
    bank_gap_count = 0
    bank_gap_amount = 0.0
    for g in bank_gap:
        jid = _m2o(g.get("journal_id"))[0]
        row = rows.get(jid)
        if row is None:
            continue
        cnt = int(g.get("__count") or 0)
        amt = float(g.get("amount") or 0.0)
        row["gap_count"] = cnt
        row["gap_amount"] = amt
        bank_gap_count += cnt
        bank_gap_amount += amt

    # Per-journal oldest gap date — bounded fetch of the bank-journal gap rows (<= ~1k).
    for grow in _fetch_all(client, "account.payment", bank_gap_dom,
                           ["journal_id", "date"], order="date asc"):
        jid = _m2o(grow.get("journal_id"))[0]
        row = rows.get(jid)
        if row is not None and row["oldest_gap_date"] is None:
            row["oldest_gap_date"] = _parse_date(grow.get("date"))
    # Per-journal last movement date (all-history) — read_group date:max where supported,
    # silently degrades to None if the ORM rejects an aggregate on the delegated field.
    try:
        for g in _read_group(client, "account.payment",
                             posted + [("journal_id", "in", real_ids)] + co_dom,
                             ["date:max"], ["journal_id"]):
            jid = _m2o(g.get("journal_id"))[0]
            row = rows.get(jid)
            if row is not None:
                row["last_movement_date"] = _parse_date(g.get("date_max") or g.get("date"))
    except Exception:
        pass

    by_bank = []
    for row in rows.values():
        row["movements_amount"] = round(row["movements_amount"], 2)
        row["inbound_amount"] = round(row["inbound_amount"], 2)
        row["outbound_amount"] = round(row["outbound_amount"], 2)
        row["gap_amount"] = round(row["gap_amount"], 2)
        row["last_movement_date"] = row["last_movement_date"].isoformat() if row["last_movement_date"] else None
        row["oldest_gap_date"] = row["oldest_gap_date"].isoformat() if row["oldest_gap_date"] else None
        row["status"] = "has_gaps" if row["gap_count"] > 0 else "clean"
        by_bank.append(row)
    by_bank.sort(key=lambda r: (-r["gap_amount"], -r["gap_count"]))

    # ── MOVEMENTS LIST (paginated) ────────────────────────────────────────────────
    # gaps_only=true → unreconciled backlog, oldest-first, date-INDEPENDENT (a gap can be
    # months old). gaps_only=false → all posted movements in the window, newest-first.
    ref_fields = _available_payment_ref_fields(client)
    mv_fields = ["id", "date", "journal_id", "company_id", "partner_id",
                 "payment_type", "amount", "is_reconciled", "is_matched", "state"]
    mv_fields += sorted(ref_fields)
    if filters.gaps_only:
        list_dom = gap_dom
        list_order = "date asc, id asc"
    else:
        list_dom = mv_dom
        list_order = "date desc, id desc"
    movements_total_count = client.search_count("account.payment", list_dom)
    movement_rows = client.search_read(
        "account.payment", domain=list_dom, fields=mv_fields,
        limit=filters.limit, offset=filters.offset, order=list_order)
    movements = []
    for m in movement_rows:
        jid, jname = _m2o(m.get("journal_id"))
        ref = ""
        for f in _CANDIDATE_PAYMENT_REF_FIELDS:
            if m.get(f):
                ref = m.get(f)
                break
        d = _parse_date(m.get("date"))
        movements.append({
            "id": m["id"],
            "date": d.isoformat() if d else None,
            "journal_id": jid,
            "bank": jname or "—",
            "is_bank_journal": jid in jmeta,
            "company": _m2o(m.get("company_id"))[1],
            "partner": _m2o(m.get("partner_id"))[1] or "—",
            "payment_type": m.get("payment_type") or "",
            "amount": round(float(m.get("amount") or 0.0), 2),
            "is_reconciled": bool(m.get("is_reconciled")),
            "is_matched": bool(m.get("is_matched")),
            "ref": ref or "",
            "state": m.get("state") or "",
        })

    # ── SUSPENSE (separate gap type — money parked, sized by NET balance) ──────────
    susp_accts = _resolve_suspense_accounts(client, company_id, cls["journal_suspense_ids"])
    suspense = []
    suspense_net_balance = 0.0
    suspense_nonzero_lines = 0
    if susp_accts:
        susp_ids = list(susp_accts.keys())
        base = [("account_id", "in", susp_ids), ("parent_state", "=", "posted")]
        # Net balance + total line count per account (reconcile=False → balance, never residual).
        net_by_acct: dict = {}
        for g in _read_group(client, "account.move.line", base, ["balance:sum"], ["account_id"]):
            aid = _m2o(g.get("account_id"))[0]
            net_by_acct[aid] = {"net": float(g.get("balance") or 0.0),
                                "lines": int(g.get("__count") or 0)}
        # Non-zero-balance line count per account.
        nonzero_by_acct: dict = {}
        for g in _read_group(client, "account.move.line", base + [("balance", "!=", 0)],
                             ["balance:sum"], ["account_id"]):
            aid = _m2o(g.get("account_id"))[0]
            nonzero_by_acct[aid] = int(g.get("__count") or 0)
        # Oldest non-zero line per account — bounded fetch (~1.8k lines all-companies).
        oldest_by_acct: dict = {}
        for ln in _fetch_all(client, "account.move.line", base + [("balance", "!=", 0)],
                             ["account_id", "date"], order="date asc"):
            aid = _m2o(ln.get("account_id"))[0]
            if aid not in oldest_by_acct:
                oldest_by_acct[aid] = _parse_date(ln.get("date"))
        for aid, meta in susp_accts.items():
            net = round(net_by_acct.get(aid, {}).get("net", 0.0), 2)
            nonzero = nonzero_by_acct.get(aid, 0)
            oldest = oldest_by_acct.get(aid)
            suspense_net_balance += net
            suspense_nonzero_lines += nonzero
            suspense.append({
                "account_id": aid, "account_code": meta["code"], "account_name": meta["name"],
                "company": meta["company"], "company_id": meta["company_id"],
                "net_balance": net, "nonzero_line_count": nonzero,
                "total_line_count": net_by_acct.get(aid, {}).get("lines", 0),
                "oldest_nonzero_date": oldest.isoformat() if oldest else None,
            })
        suspense.sort(key=lambda r: -abs(r["net_balance"]))
    suspense_net_balance = round(suspense_net_balance, 2)

    # ── DRAFT BANK MOVES (awareness — unposted bank journal entries) ───────────────
    draft_dom = [("journal_id", "in", real_ids), ("state", "=", "draft")] + co_dom
    draft_bank_moves = []
    draft_total_count = 0
    for g in _read_group(client, "account.move", draft_dom, ["amount_total:sum"], ["company_id"]):
        cid, cname = _m2o(g.get("company_id"))
        cnt = int(g.get("__count") or 0)
        draft_total_count += cnt
        draft_bank_moves.append({
            "company_id": cid, "company": cname,
            "count": cnt, "amount": round(float(g.get("amount_total") or 0.0), 2),
        })

    summary = {
        # MOVEMENT volume — within the selected date window.
        "total_movements_count": mv_tot["count"],
        "total_inbound_amount": round(mv_tot["inbound_amount"], 2),
        "total_outbound_amount": round(mv_tot["outbound_amount"], 2),
        # GAP totals — full-history "as of today", all journals (the backlog headline).
        "gap_count": gap_tot["count"],
        "gap_amount": round(gap_tot["amount"], 2),
        "gap_inbound_amount": round(gap_tot["inbound_amount"], 2),
        "gap_outbound_amount": round(gap_tot["outbound_amount"], 2),
        # Subtotal of the gap that sits on the 27 REAL bank journals (ties to by_bank).
        "gap_count_on_bank_journals": bank_gap_count,
        "gap_amount_on_bank_journals": round(bank_gap_amount, 2),
        # Suspense (separate gap type) + drafts.
        "suspense_net_balance": suspense_net_balance,
        "suspense_nonzero_lines": suspense_nonzero_lines,
        "oldest_gap_date": oldest_gap_date.isoformat() if oldest_gap_date else None,
        "draft_bank_moves_count": draft_total_count,
        "as_of": now_utc.isoformat(),
    }

    return {
        **base_block,
        "summary": summary,
        "by_bank": by_bank,
        "movements": movements,
        "movements_total_count": movements_total_count,
        "movements_offset": filters.offset,
        "movements_limit": filters.limit,
        "suspense": suspense,
        "draft_bank_moves": draft_bank_moves,
    }


# ── Gap drill-down (one bank journal — the payments that make up its GAP) ───────────

def _empty_gap_header() -> dict:
    return {
        "bank": "—", "journal_code": "", "company": "", "company_id": None, "kind": None,
        "gap_count": 0, "gap_amount": 0.0,
        "gap_inbound_amount": 0.0, "gap_outbound_amount": 0.0,
        "oldest_gap_date": None,
    }


def _map_payment_row(m: dict, jmeta: dict) -> dict:
    """Shape one ``account.payment`` record exactly like the main movements list."""
    jid, jname = _m2o(m.get("journal_id"))
    ref = ""
    for f in _CANDIDATE_PAYMENT_REF_FIELDS:
        if m.get(f):
            ref = m.get(f)
            break
    d = _parse_date(m.get("date"))
    return {
        "id": m["id"],
        "date": d.isoformat() if d else None,
        "journal_id": jid,
        "bank": jname or "—",
        "is_bank_journal": jid in jmeta,
        "company": _m2o(m.get("company_id"))[1],
        "partner": _m2o(m.get("partner_id"))[1] or "—",
        "payment_type": m.get("payment_type") or "",
        "amount": round(float(m.get("amount") or 0.0), 2),
        "is_reconciled": bool(m.get("is_reconciled")),
        "is_matched": bool(m.get("is_matched")),
        "ref": ref or "",
        "state": m.get("state") or "",
    }


def compute_bank_gap_detail(client, filters: BankGapDetailFilter) -> dict:
    """Drill-down for ONE bank journal: the unreconciled posted ``account.payment``
    movements that make up that journal's GAP, oldest-first (oldest backlog at top).

    Mirrors the main screen's per-bank gap EXACTLY for this one journal so the numbers
    tie out. The header ``gap_count``/``gap_amount`` use the SAME domain the main
    ``by_bank`` table groups over — ``state='posted' ∧ is_reconciled=False ∧
    journal_id=<this journal>`` (respecting ``company_id``) — so they are identical to
    that journal's row on the main screen for the same scope.

    INVARIANT: header.gap_count == by_bank[journal].gap_count, header.gap_amount ==
    by_bank[journal].gap_amount, and movements total_count == gap_count. Graceful empty
    (HTTP 200) when the journal carries no gap, or is not one of the real bank journals
    in the requested scope (e.g. a Visa-holding journal, or a journal of another company).
    """
    now_utc = datetime.now(timezone.utc)
    company_id = filters.company_id
    journal_id = filters.journal_id

    # Same classification the main screen uses — so we attribute the journal identically
    # (real bank vs Visa-holding) and reuse its name/code/company/kind metadata.
    cls = _classify_bank_journals(client, company_id)
    jmeta = {r["journal_id"]: r for r in cls["real"]}

    base = {
        "as_of": now_utc.isoformat(),
        "company_id": company_id,
        "journal_id": journal_id,
        "header": _empty_gap_header(),
        "movements": [],
        "total_count": 0,
        "offset": filters.offset,
        "limit": filters.limit,
    }

    meta = jmeta.get(journal_id)
    # Not a real bank journal in this scope (Visa-holding / wrong company) → graceful empty,
    # consistent with the main by_bank table (which would not list it either).
    if meta is None:
        return base

    co_dom = _company_domain(company_id)
    # IDENTICAL domain to the main screen's per-journal gap (bank_gap_dom restricted to
    # this journal) — this is what guarantees the header totals tie to by_bank.
    gap_dom = [("state", "=", "posted"), ("is_reconciled", "=", False),
               ("journal_id", "=", journal_id)] + co_dom

    tot = _direction_totals(client, gap_dom)
    oldest_row = client.search_read(
        "account.payment", domain=gap_dom, fields=["date"], order="date asc", limit=1)
    oldest = _parse_date(oldest_row[0]["date"]) if oldest_row else None

    header = {
        "bank": meta["name"], "journal_code": meta["code"],
        "company": meta["company"], "company_id": meta["company_id"], "kind": meta["kind"],
        "gap_count": tot["count"],
        "gap_amount": round(tot["amount"], 2),
        "gap_inbound_amount": round(tot["inbound_amount"], 2),
        "gap_outbound_amount": round(tot["outbound_amount"], 2),
        "oldest_gap_date": oldest.isoformat() if oldest else None,
    }

    # Paginated movements — oldest-first (oldest backlog at top). total_count == gap_count.
    ref_fields = _available_payment_ref_fields(client)
    mv_fields = ["id", "date", "journal_id", "company_id", "partner_id",
                 "payment_type", "amount", "is_reconciled", "is_matched", "state"]
    mv_fields += sorted(ref_fields)
    total_count = client.search_count("account.payment", gap_dom)
    movement_rows = client.search_read(
        "account.payment", domain=gap_dom, fields=mv_fields,
        limit=filters.limit, offset=filters.offset, order="date asc, id asc")
    movements = [_map_payment_row(m, jmeta) for m in movement_rows]

    return {**base, "header": header, "movements": movements, "total_count": total_count}
