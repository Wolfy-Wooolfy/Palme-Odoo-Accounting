"""Visa / Card Reconciliation Monitor — collected vs confirmed vs late (Area 2).

Answers, per branch of the SELECTED company (default = 3 ``#بالميه#.``, the only
company with an active Geidea Visa-confirmation workflow): "How much Visa was
collected, how much has the accountant confirmed received from Geidea (جيديا),
what is still pending, and which branches are LATE (>2 working days after session
close with no confirmation)?" — plus the frozen company-1 legacy pile surfaced as
an awareness footnote.

100% READ-ONLY. Uses only ``search_read`` / ``read`` / ``read_group`` on the shared
OdooReadOnlyClient (the client hard-blocks every write method, and serialises RPC
dispatch internally, so we use the shared singleton like every other report).

Multi-company (the WHOLE screen scopes to the selected company — nothing is
hardcoded to company 3). Everything is DERIVED from that company's live Visa data
(see DISCOVERY_REPORT.md → "Area 2 — Visa Bank-Confirmation Mechanics" and
"Area 2 — Session→Geidea Linkage & Late Rule"):

* Scope = the company's Visa ``pos.payment.method`` set (``is_cash_count=False`` and
  name contains 'فيزا'). Its ``outstanding_account_id`` values are the holding
  accounts; its ``journal_id`` values are the branch journals. Verified live:
  company 3 → 8 branch journals (VIS01-07 + arabisck VIS99) into 2 shared holding
  accounts (17495/16823); company 1 → 39 branch journals 1:1 with 39 holding
  accounts (the frozen legacy pile); company 2 → no Visa methods (empty, graceful).
  Holding accounts are ``reconcile=False, asset_cash`` → line-level reconciliation
  does NOT exist, so confirmation is measured by the holding running BALANCE.
* Branch attribution = ``journal_id`` (NEVER ``account_id``: co3 funnels every
  branch journal into the single shared holding account 17495). Only journals in
  the company's Visa-method set are kept, which naturally drops the MISC / CSH99 /
  CSH=1 / POSS noise journals that also touch the shared holding account.
* COLLECTED (per branch) = Σ debit on the holding accounts (posted), grouped by
  journal. Each collection debit traces ``payment_id`` → ``pos_session_id`` →
  ``stop_at`` — the late clock is anchored to ``stop_at`` (the accounting ``date``
  can roll a day late for late-evening closes).
* CONFIRMED (bank receipt) = Σ credit on the holding accounts whose move has a
  **"Liquidity Transfer"** counterpart leg. This account is company-specific —
  code 63001 (id 16572) for company 3, code 101701 (id 46) for company 1 — so it is
  resolved per company by NAME ('Liquidity Transfer') ∪ the known code, never a
  hardcoded id. Non-confirmation clearings (fees/adjustments) are excluded.
* PENDING (per branch) = Σ balance = collected − all credits = the holding
  running balance (positive = collected-but-not-confirmed).
* LATE rule: FIFO-consume the oldest collections (by ``stop_at``) with everything
  that has cleared the holding account; the oldest still-unconfirmed collection
  whose ``stop_at + 2 working days < server-today`` makes the branch LATE. Working
  days skip FRIDAY only (Saturday is a working day). Over-credited branches
  (running balance < 0, e.g. co3 arabisck) carry no pending and are flagged
  ``manual`` (the 2-wd rule and the summary totals skip them).

Query strategy: account.move.line has millions of rows, so the work is BOUNDED by
the holding-account domain. A company's Visa holding accounts hold only a few
thousand posted lines all-time (co3 ~2.4k, co1 ~7.2k — both static/frozen for co1),
so a single paginated ``search_read`` over ``account_id in <holding set>`` is a
bounded fetch (capped, never a full-table scan) that drives the FIFO tail, the
per-branch totals and the daily grid without N per-branch round-trips. The legacy
awareness total uses ``read_group``. Do NOT copy this to an un-scoped move-line query.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from api.models.visa import VisaBranchDetailFilter, VisaReconFilter

# ── Company scope ───────────────────────────────────────────────────────────────
DEFAULT_COMPANY_ID = 3            # only company with an active Geidea Visa workflow
LEGACY_COMPANY_ID = 1             # the frozen ~107M legacy Visa pile (awareness footnote)

# Active co-3 Visa holding accounts — a verified safety anchor unioned into the
# live method-derivation for company 3 only (the derivation already returns these).
CO3_HOLDING_ANCHORS = [17495, 16823]

# Full Visa holding-account set (41 accounts) — legacy fallback only, if the live
# pos.payment.method derivation for company 1 comes back empty.
_ALL_VISA_HOLDING_FALLBACK = (
    [85, 86, 87, 88, 89, 90, 316]
    + list(range(365, 386))      # 365-385
    + list(range(394, 401))      # 394-400
    + [961, 962, 16823, 17412, 17416, 17495]
)

# "Liquidity Transfer" = the bank-bound confirmation counterpart. Company-specific:
# resolved per company by NAME ∪ known code (co3 63001/16572, co1 101701/46).
LIQUIDITY_NAME = "Liquidity Transfer"
LIQUIDITY_CODE = "63001"          # co3 anchor code (unioned into the per-company lookup)
LIQUIDITY_ID_FALLBACK = 16572     # co3 id, last-resort fallback only

VISA_METHOD_NAME = "فيزا"         # non-cash POS methods named 'فيزا' define the Visa scope
LATE_WORKING_DAYS = 2
FRIDAY = 4                        # date.weekday(): Mon=0 … Fri=4 … Sun=6 (Friday = only weekend)

_LEGACY_STALLED_DAYS = 30         # legacy pile flagged "stalled" if no confirmation in this many days


# ── Pure helpers (no Odoo) — exercised by test_visa_fifo.py ─────────────────────

def is_working_day(d: date) -> bool:
    """Friday is the ONLY weekend day here; Saturday is a working day."""
    return d.weekday() != FRIDAY


def working_days_between(start: date, end: date) -> int:
    """Number of working days strictly after ``start`` up to and including ``end``.

    Counting begins the day AFTER ``start`` and skips Fridays only. Returns 0 when
    ``end <= start``. So a session closed Wed 2026-06-17, measured on Tue 2026-06-23,
    is 5 working days old (skipping Fri 06-19) — matching the discovery's worked
    examples. LATE ⇔ ``working_days_between(stop_at, today) > 2``.
    """
    if end <= start:
        return 0
    count = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if is_working_day(d):
            count += 1
    return count


def oldest_unconfirmed(collections, settled_total, eps: float = 0.01):
    """FIFO-consume oldest collections with the cumulative settlement pool.

    ``collections`` = list of ``(stop_at_date, amount)``, oldest first. Returns the
    ``stop_at_date`` of the oldest collection NOT fully covered by ``settled_total``,
    or ``None`` when every collection is covered. Settlements arrive as periodic lumps
    per branch (not per session), so we settle oldest-first rather than trying a
    (structurally impossible) per-session match. ``settled_total`` is everything that
    has cleared the holding account (transfer + fee), so the unconsumed tail equals the
    branch's running balance.
    """
    pool = settled_total
    for stop_at, amount in collections:  # oldest first
        if pool + eps >= amount:
            pool -= amount
        else:
            return stop_at
    return None


# ── Odoo plumbing helpers ───────────────────────────────────────────────────────

def _m2o(value) -> tuple:
    """Split an Odoo many2one ``[id, name]`` pair into ``(id, name)``."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    return None, ""


def _parse_utc(value) -> datetime | None:
    """Parse a stored Odoo datetime ('YYYY-MM-DD HH:MM:SS', UTC) as tz-aware UTC."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_date(value) -> date | None:
    """Parse a stored Odoo date ('YYYY-MM-DD'). Tolerates a full datetime string."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_all(client, model, domain, fields, *, order=None, batch=2000, hard_cap=50000):
    """Paginated search_read — the client default limit is 80, so page explicitly.

    BOUNDED by the caller's domain (never an open scan). ``hard_cap`` is a runaway
    backstop: the co-3 holding set is ~2.4k lines, so this never approaches it.
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


def _resolve_visa_scope(client, company_id: int) -> tuple[list[int], set]:
    """Resolve a company's Visa scope from its POS payment methods.

    Returns ``(holding_account_ids, branch_journal_ids)`` — the
    ``outstanding_account_id`` and ``journal_id`` of every non-cash ``pos.payment.method``
    named 'فيزا' under ``company_id``. This is the discovery's own definition and is
    fully company-agnostic (co3 → 2 accounts / 8 journals; co1 → 39 / 39; co2 → none).
    For company 3 the two verified holding anchors are unioned in for safety.
    """
    holding: set = set()
    journals: set = set()
    try:
        methods = client.search_read(
            "pos.payment.method",
            domain=[("is_cash_count", "=", False), ("name", "like", VISA_METHOD_NAME),
                    ("company_id", "=", company_id)],
            fields=["id", "outstanding_account_id", "journal_id"], limit=500,
        )
        for m in methods:
            acct = _m2o(m.get("outstanding_account_id"))[0]
            jid = _m2o(m.get("journal_id"))[0]
            if acct:
                holding.add(acct)
            if jid:
                journals.add(jid)
    except Exception:
        pass
    if company_id == DEFAULT_COMPANY_ID:
        holding |= set(CO3_HOLDING_ANCHORS)
    return sorted(holding), journals


def _resolve_liquidity_accounts(client, company_id: int) -> set:
    """The company's "Liquidity Transfer" account ids — the bank-bound confirmation
    counterpart. Resolved by NAME ∪ the co3 anchor code (company 3 = 63001/16572,
    company 1 = 101701/46), filtered to the company. Falls back to the co3 id.
    """
    ids: set = set()
    try:
        rows = client.search_read(
            "account.account",
            domain=["&", ("company_id", "=", company_id),
                    "|", ("name", "ilike", LIQUIDITY_NAME), ("code", "=", LIQUIDITY_CODE)],
            fields=["id"], limit=50,
        )
        ids = {r["id"] for r in rows}
    except Exception:
        pass
    return ids or {LIQUIDITY_ID_FALLBACK}


def _resolve_legacy_holding(client) -> list[int]:
    """Legacy (company-1) Visa holding accounts = outstanding_account_id of every
    non-cash POS payment method named 'فيزا' under company 1 (discovery's own
    definition). Falls back to the verified 41-account list minus the co-3 anchors.
    """
    legacy: set = set()
    try:
        methods = client.search_read(
            "pos.payment.method",
            domain=[("is_cash_count", "=", False), ("name", "like", "فيزا"),
                    ("company_id", "=", LEGACY_COMPANY_ID)],
            fields=["id", "outstanding_account_id"], limit=500,
        )
        for m in methods:
            acct = _m2o(m.get("outstanding_account_id"))[0]
            if acct:
                legacy.add(acct)
    except Exception:
        pass
    if not legacy:
        legacy = set(_ALL_VISA_HOLDING_FALLBACK) - set(CO3_HOLDING_ANCHORS)
    legacy -= set(CO3_HOLDING_ANCHORS)  # never let an active co-3 account into the legacy pile
    return sorted(legacy)


def _confirmation_moves(client, move_ids, liq_ids) -> set:
    """The holding-credit moves that are bank confirmations = those with a
    "Liquidity Transfer" counterpart leg.

    The Geidea settlement posts the transfer (CR holding / DR Liquidity Transfer)
    and the fee (CR holding / DR commission) as SEPARATE moves, so the transfer move
    is identified by its liquidity leg; fee/adjustment credits are not confirmations.
    Bounded: only the (few hundred) credit-bearing moves are inspected, each
    restricted to its liquidity legs.
    """
    confirmation: set = set()
    if not move_ids:
        return confirmation
    legs = _fetch_all(
        client, "account.move.line",
        [("move_id", "in", list(move_ids)), ("account_id", "in", list(liq_ids))],
        ["move_id", "account_id"],
    )
    for leg in legs:
        confirmation.add(_m2o(leg.get("move_id"))[0])
    return confirmation


def _map_stop_at(client, debit_lines) -> dict:
    """Map each collection debit line id → its session ``stop_at`` date.

    Walks ``payment_id`` → ``account.payment.pos_session_id`` → ``pos.session.stop_at``.
    Falls back to the line's accounting date for any non-session debit (e.g. a manual
    adjustment with no payment). All lookups are id-bounded.
    """
    payment_ids = sorted({_m2o(l.get("payment_id"))[0] for l in debit_lines if l.get("payment_id")})

    sess_by_payment: dict = {}
    if payment_ids:
        for p in _fetch_all(client, "account.payment",
                            [("id", "in", payment_ids)], ["id", "pos_session_id"]):
            sid = _m2o(p.get("pos_session_id"))[0]
            if sid:
                sess_by_payment[p["id"]] = sid

    stop_by_session: dict = {}
    session_ids = sorted(set(sess_by_payment.values()))
    if session_ids:
        for s in _fetch_all(client, "pos.session",
                            [("id", "in", session_ids)], ["id", "stop_at"]):
            d = _parse_utc(s.get("stop_at"))
            if d:
                stop_by_session[s["id"]] = d.date()

    out: dict = {}
    for l in debit_lines:
        pid = _m2o(l.get("payment_id"))[0]
        sid = sess_by_payment.get(pid)
        stop = stop_by_session.get(sid) if sid else None
        out[l["id"]] = stop or _parse_date(l.get("date"))
    return out


def _map_session_info(client, debit_lines) -> dict:
    """Map each collection debit line id → its session info for the drill-down.

    Same dot-walk as :func:`_map_stop_at` (``payment_id`` →
    ``account.payment.pos_session_id`` → ``pos.session``) but also carries the session
    NAME and its POS ``config_id`` (the branch label), so the per-session drill-down can
    show "which session" and "which branch". For any non-session debit (a manual
    adjustment with no payment) ``session_id`` is ``None`` and ``stop_at`` falls back to
    the line's accounting date — keeping it in the FIFO so residuals still reconcile to
    pending. All lookups are id-bounded.

    Returns ``{line_id: {"session_id", "session_name", "config", "stop_at"}}``.
    """
    payment_ids = sorted({_m2o(l.get("payment_id"))[0] for l in debit_lines if l.get("payment_id")})

    sess_by_payment: dict = {}
    if payment_ids:
        for p in _fetch_all(client, "account.payment",
                            [("id", "in", payment_ids)], ["id", "pos_session_id"]):
            sid = _m2o(p.get("pos_session_id"))[0]
            if sid:
                sess_by_payment[p["id"]] = sid

    sess_meta: dict = {}
    session_ids = sorted(set(sess_by_payment.values()))
    if session_ids:
        for s in _fetch_all(client, "pos.session",
                            [("id", "in", session_ids)], ["id", "name", "config_id", "stop_at"]):
            d = _parse_utc(s.get("stop_at"))
            sess_meta[s["id"]] = {
                "name": s.get("name") or f"#{s['id']}",
                "config": _m2o(s.get("config_id"))[1],
                "stop_at": d.date() if d else None,
            }

    out: dict = {}
    for l in debit_lines:
        pid = _m2o(l.get("payment_id"))[0]
        sid = sess_by_payment.get(pid)
        meta = sess_meta.get(sid) if sid else None
        if meta:
            out[l["id"]] = {
                "session_id": sid,
                "session_name": meta["name"],
                "config": meta["config"],
                "stop_at": meta["stop_at"] or _parse_date(l.get("date")),
            }
        else:
            out[l["id"]] = {
                "session_id": None,
                "session_name": l.get("name") or None,
                "config": None,
                "stop_at": _parse_date(l.get("date")),
            }
    return out


def _legacy_awareness(client, today: date) -> dict:
    """Small read-only awareness block for the frozen company-1 legacy pile.

    Totals only (no per-line work): the legacy accounts hold ~7k lines, so we
    aggregate with ``read_group`` and take the most-recent credit date as a
    confirmation proxy. Per discovery this pile is ~107M net and stalled since
    ~2025-09-25.
    """
    legacy_ids = _resolve_legacy_holding(client)
    empty = {
        "total_net_pending": 0.0, "total_collected": 0.0, "total_confirmed": 0.0,
        "last_confirmation_date": None, "days_since_last_confirmation": None,
        "stalled": False, "account_count": 0,
    }
    if not legacy_ids:
        return empty

    domain = [("account_id", "in", legacy_ids), ("parent_state", "=", "posted"),
              ("company_id", "=", LEGACY_COMPANY_ID)]
    grp = client.execute_kw(
        "account.move.line", "read_group",
        [domain, ["debit:sum", "credit:sum", "balance:sum"], []],
        {"lazy": False},
    )
    row = grp[0] if grp else {}
    collected = float(row.get("debit") or 0.0)
    confirmed = float(row.get("credit") or 0.0)
    net = float(row.get("balance") or 0.0)

    last = client.search_read(
        "account.move.line",
        domain=[("account_id", "in", legacy_ids), ("parent_state", "=", "posted"),
                ("credit", ">", 0)],
        fields=["date"], order="date desc", limit=1,
    )
    last_d = _parse_date(last[0]["date"]) if last else None
    days_since = (today - last_d).days if last_d else None
    return {
        "total_net_pending": round(net, 2),
        "total_collected": round(collected, 2),
        "total_confirmed": round(confirmed, 2),
        "last_confirmation_date": last_d.isoformat() if last_d else None,
        "days_since_last_confirmation": days_since,
        "stalled": bool(days_since is not None and days_since > _LEGACY_STALLED_DAYS),
        "account_count": len(legacy_ids),
    }


# ── Main entry point ────────────────────────────────────────────────────────────

def _empty_summary() -> dict:
    return {
        "total_pending": 0.0, "total_collected": 0.0, "total_confirmed": 0.0,
        "late_branches_count": 0, "active_branches_count": 0,
        "oldest_unconfirmed_stop_at": None, "oldest_unconfirmed_working_days": 0,
        "last_confirmation_date": None,
    }


def compute_visa_reconciliation(client, filters: VisaReconFilter) -> dict:
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()  # server-today; stored stop_at/date are UTC, so compare in UTC

    # The WHOLE screen scopes to the selected company; default to 3 (the only one
    # with a live Geidea Visa-confirmation workflow) when none is chosen.
    company_id = filters.company_id or DEFAULT_COMPANY_ID
    is_default = filters.company_id is None

    # daily_detail window (the ONLY block the date filter touches). Default 30 days.
    date_to = filters.date_to or today
    date_from = filters.date_from or (date_to - timedelta(days=30))
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    # Resolve THIS company's Visa scope from its POS methods (holding accounts +
    # branch journals) — nothing hardcoded to company 3.
    holding_ids, branch_journals = _resolve_visa_scope(client, company_id)

    # Company with no Visa workflow (e.g. company 2) → graceful empty blocks (HTTP 200).
    if not holding_ids:
        return {
            "as_of": now_utc.isoformat(),
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "company_id": company_id,
            "is_default_company": is_default,
            "summary": _empty_summary(),
            "by_branch": [],
            "daily_detail": [],
            "legacy_awareness": _legacy_awareness(client, today),
        }

    liq_ids = _resolve_liquidity_accounts(client, company_id)

    # ── One bounded fetch of every posted holding line for this company (co3 ~2.4k,
    #    co1 ~7.2k — bounded by the holding-account domain, capped) ──────────────────
    lines = _fetch_all(
        client, "account.move.line",
        domain=[("account_id", "in", holding_ids), ("parent_state", "=", "posted"),
                ("company_id", "=", company_id)],
        fields=["id", "journal_id", "account_id", "date", "debit", "credit",
                "balance", "move_id", "payment_id"],
        order="date asc, id asc",
    )

    # Confirmation moves (have a Liquidity-Transfer leg) + tag debit lines with stop_at.
    credit_move_ids = {_m2o(l["move_id"])[0] for l in lines
                       if (l.get("credit") or 0) > 0 and l.get("move_id")}
    confirmation_moves = _confirmation_moves(client, credit_move_ids, liq_ids)
    debit_lines = [l for l in lines if (l.get("debit") or 0) > 0]
    stop_at_by_line = _map_stop_at(client, debit_lines)

    # Journal metadata (code + name) for the journals touching the holding accounts.
    journal_ids = sorted({_m2o(l["journal_id"])[0] for l in lines if l.get("journal_id")})
    journal_meta: dict = {}
    if journal_ids:
        for j in client.read("account.journal", journal_ids, ["code", "name"]):
            journal_meta[j["id"]] = {"code": j.get("code") or "", "name": j.get("name") or ""}

    # ── Aggregate per branch journal (only the company's Visa-method journals; this
    #    drops the MISC / CSH99 / CSH=1 / POSS noise journals on the shared account) ─
    branches: dict = {}
    for l in lines:
        jid = _m2o(l["journal_id"])[0]
        if jid not in branch_journals:
            continue
        meta = journal_meta.get(jid, {})
        b = branches.setdefault(jid, {
            "journal_id": jid, "journal_code": meta.get("code", ""),
            "branch": meta.get("name") or meta.get("code") or "—",
            "collected": 0.0, "confirmed": 0.0, "balance": 0.0,
            "collections": [], "confirm_dates": [],
        })
        debit = float(l.get("debit") or 0.0)
        credit = float(l.get("credit") or 0.0)
        b["balance"] += float(l.get("balance") or 0.0)
        mid = _m2o(l["move_id"])[0]
        if debit > 0:
            b["collected"] += debit
            b["collections"].append((stop_at_by_line.get(l["id"]), debit))
        elif credit > 0 and mid in confirmation_moves:
            b["confirmed"] += credit
            d = _parse_date(l.get("date"))
            if d:
                b["confirm_dates"].append(d)

    by_branch: list[dict] = []
    for jid, b in branches.items():
        # Over-credited branches (running balance < 0, e.g. co3 arabisck) carry no
        # pending — you can't be "late" on money you've over-confirmed — so they are
        # flagged `manual`: the 2-wd FIFO rule and the summary totals skip them.
        is_manual = b["balance"] < -0.01
        cols = sorted(((sd, amt) for (sd, amt) in b["collections"] if sd is not None),
                      key=lambda x: x[0])
        # FIFO consumes collections with everything that has CLEARED the holding
        # account = Σ all credits = collected − running balance. A day's takings settle
        # only once the transfer AND its fee post; consuming with the transfer alone
        # would leave a phantom fee-sized tail and overstate "oldest unconfirmed".
        # Using all clearing credits makes the unconsumed tail equal `pending` exactly.
        # (total_confirmed — the bank-receipt KPI — stays Liquidity-Transfer-only.)
        settled_total = b["collected"] - b["balance"]
        oldest = None if is_manual else oldest_unconfirmed(cols, settled_total)
        wd = working_days_between(oldest, today) if oldest else 0
        if is_manual:
            status = "manual"
        elif oldest is None:
            status = "ok"
        elif wd > LATE_WORKING_DAYS:
            status = "late"
        else:
            status = "due_soon"
        last_conf = max(b["confirm_dates"]) if b["confirm_dates"] else None
        by_branch.append({
            "journal_id": jid,
            "journal_code": b["journal_code"],
            "branch": b["branch"],
            "collected": round(b["collected"], 2),
            "confirmed": round(b["confirmed"], 2),
            "commission": round(settled_total - b["confirmed"], 2),  # fees/adjustments (informational)
            "pending": round(b["balance"], 2),
            "last_confirmation_date": last_conf.isoformat() if last_conf else None,
            "oldest_unconfirmed_stop_at": oldest.isoformat() if oldest else None,
            "working_days_since_oldest_unconfirmed": wd,
            "status": status,
            "manually_handled": is_manual,
        })
    # Late first, then by pending desc; manual (over-credited) sinks to the bottom.
    _rank = {"late": 0, "due_soon": 1, "ok": 2, "manual": 3}
    by_branch.sort(key=lambda r: (_rank.get(r["status"], 9), -r["pending"]))

    # ── Summary (active branches only; over-credited/manual rows excluded) ─────────
    active = [r for r in by_branch if not r["manually_handled"]]
    oldest_dates = [r["oldest_unconfirmed_stop_at"] for r in active if r["oldest_unconfirmed_stop_at"]]
    global_oldest = min(oldest_dates) if oldest_dates else None
    confirm_dates = [
        _parse_date(l["date"]) for l in lines
        if (l.get("credit") or 0) > 0 and _m2o(l["move_id"])[0] in confirmation_moves
    ]
    confirm_dates = [d for d in confirm_dates if d]
    summary = {
        "total_pending": round(sum(r["pending"] for r in active), 2),
        "total_collected": round(sum(r["collected"] for r in active), 2),
        "total_confirmed": round(sum(r["confirmed"] for r in active), 2),
        "late_branches_count": sum(1 for r in active if r["status"] == "late"),
        "active_branches_count": len(active),
        "oldest_unconfirmed_stop_at": global_oldest,
        "oldest_unconfirmed_working_days": (
            working_days_between(_parse_date(global_oldest), today) if global_oldest else 0),
        "last_confirmation_date": max(confirm_dates).isoformat() if confirm_dates else None,
    }

    # ── daily_detail (date-filtered): per branch per day collected/confirmed/net ───
    daily: dict = {}
    for l in lines:
        d = _parse_date(l.get("date"))
        if d is None or d < date_from or d > date_to:
            continue
        jid = _m2o(l["journal_id"])[0]
        if jid not in branch_journals:
            continue
        meta = journal_meta.get(jid, {})
        cell = daily.setdefault((jid, d), {
            "journal_id": jid, "journal_code": meta.get("code", ""),
            "branch": meta.get("name") or meta.get("code") or "—", "date": d.isoformat(),
            "collected": 0.0, "confirmed": 0.0,
        })
        debit = float(l.get("debit") or 0.0)
        credit = float(l.get("credit") or 0.0)
        if debit > 0:
            cell["collected"] += debit
        elif credit > 0 and _m2o(l["move_id"])[0] in confirmation_moves:
            cell["confirmed"] += credit
    daily_detail = []
    for cell in daily.values():
        cell["collected"] = round(cell["collected"], 2)
        cell["confirmed"] = round(cell["confirmed"], 2)
        cell["net"] = round(cell["collected"] - cell["confirmed"], 2)
        daily_detail.append(cell)
    daily_detail.sort(key=lambda r: (r["date"], r["branch"]), reverse=True)

    return {
        "as_of": now_utc.isoformat(),
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "company_id": company_id,
        "is_default_company": is_default,
        "summary": summary,
        "by_branch": by_branch,
        "daily_detail": daily_detail,
        "legacy_awareness": _legacy_awareness(client, today),
    }


# ── Branch drill-down (Phase 3B+) ────────────────────────────────────────────────

RECENT_CONFIRMATIONS_LIMIT = 12   # how many recent Geidea settlement credits to surface


def _empty_branch_header() -> dict:
    return {
        "collected": 0.0, "confirmed": 0.0, "commission": 0.0, "pending": 0.0,
        "unconfirmed_sessions_count": 0, "oldest_unconfirmed_stop_at": None,
        "oldest_unconfirmed_working_days": 0, "status": "ok", "manually_handled": False,
    }


def compute_visa_branch_detail(client, filters: VisaBranchDetailFilter) -> dict:
    """Session-level drill-down for ONE branch journal — the sessions that make up
    that branch's pending (collected-but-unconfirmed) holding balance.

    Mirrors the main screen's compute EXACTLY for this one journal so the numbers tie
    out: same scope resolution, same liquidity (``63001``) confirmation detection, same
    FIFO with the full clearing-credit pool (transfer + commission). The only new work
    is splitting each holding **debit** back to its POS session (via ``payment_id``) and
    distributing the FIFO settlement across those sessions oldest-first, so each session
    gets a ``confirmed`` (covered) and a ``residual_unconfirmed`` slice.

    INVARIANT: ``Σ residual_unconfirmed`` over the returned sessions == this branch's
    ``pending`` on the main screen (to the cent). Both equal the holding running balance
    ``Σ debit − Σ all credits`` — the FIFO only RE-SLICES that same total across sessions.

    Returns the unconfirmed/partially-confirmed sessions (residual > 0) only — the
    fully-settled history is irrelevant to "what's still pending" and would bury the
    answer under hundreds of confirmed rows. Oldest-first ⇒ the oldest unconfirmed
    session is at the top. Graceful empty (HTTP 200) when nothing is pending.
    """
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    company_id = filters.company_id
    journal_id = filters.journal_id

    holding_ids, branch_journals = _resolve_visa_scope(client, company_id)

    base = {
        "as_of": now_utc.isoformat(),
        "company_id": company_id,
        "journal_id": journal_id,
        "branch": "—",
        "journal_code": "",
        "header": _empty_branch_header(),
        "sessions": [],
        "recent_confirmations": [],
    }

    # Unknown company (no Visa workflow) or a journal that isn't one of this company's
    # Visa branch journals (e.g. the MISC/CSH noise journals) → graceful empty.
    if not holding_ids or journal_id not in branch_journals:
        return base

    liq_ids = _resolve_liquidity_accounts(client, company_id)

    # Bounded fetch: only THIS branch journal's posted holding lines.
    lines = _fetch_all(
        client, "account.move.line",
        domain=[("account_id", "in", holding_ids), ("parent_state", "=", "posted"),
                ("company_id", "=", company_id), ("journal_id", "=", journal_id)],
        fields=["id", "date", "debit", "credit", "balance", "move_id", "payment_id", "name"],
        order="date asc, id asc",
    )

    jmeta = {"code": "", "name": ""}
    for j in client.read("account.journal", [journal_id], ["code", "name"]):
        jmeta = {"code": j.get("code") or "", "name": j.get("name") or ""}
    branch_name = jmeta["name"] or jmeta["code"] or "—"

    if not lines:
        return {**base, "branch": branch_name, "journal_code": jmeta["code"]}

    # Confirmation moves (have a 63001 "Liquidity Transfer" leg) among this branch's
    # credit moves — a move's liquidity-leg status is branch-independent, so restricting
    # to this branch's credit moves yields the same classification as the main screen.
    credit_move_ids = {_m2o(l["move_id"])[0] for l in lines
                       if (l.get("credit") or 0) > 0 and l.get("move_id")}
    confirmation_moves = _confirmation_moves(client, credit_move_ids, liq_ids)

    debit_lines = [l for l in lines if (l.get("debit") or 0) > 0]
    sess_info = _map_session_info(client, debit_lines)

    collected = sum(float(l.get("debit") or 0.0) for l in debit_lines)
    balance = sum(float(l.get("balance") or 0.0) for l in lines)        # == pending on main screen
    confirmed = sum(float(l.get("credit") or 0.0) for l in lines        # 63001-only bank-receipt KPI
                    if (l.get("credit") or 0) > 0 and _m2o(l["move_id"])[0] in confirmation_moves)
    settled_total = collected - balance                                  # all clearing credits (FIFO pool)
    is_manual = balance < -0.01                                          # over-credited → no pending

    # Aggregate the per-session collection debits (a session can post >1 debit line; they
    # share a stop_at, so this never changes the FIFO order or totals). Non-session debits
    # each get their own bucket so nothing is dropped from the pending total.
    sess_agg: dict = {}
    for l in debit_lines:
        info = sess_info[l["id"]]
        sid = info["session_id"]
        key = sid if sid is not None else f"line-{l['id']}"
        a = sess_agg.setdefault(key, {
            "session_id": sid,
            "session_name": info["session_name"] or (f"#{sid}" if sid else "—"),
            "config": info["config"],
            "stop_at": info["stop_at"],
            "collected": 0.0,
        })
        a["collected"] += float(l.get("debit") or 0.0)
        if a["stop_at"] is None:
            a["stop_at"] = info["stop_at"]

    # FIFO: consume the clearing pool against sessions oldest-first (by stop_at). Sessions
    # with no stop_at sort last. Each session keeps the slice the pool couldn't cover.
    sessions_sorted = sorted(sess_agg.values(), key=lambda s: (s["stop_at"] or date.max))
    pool = settled_total
    pending_rows: list[dict] = []
    oldest_date: date | None = None
    for s in sessions_sorted:
        col = s["collected"]
        consume = min(pool, col) if pool > 0 else 0.0
        if consume < 0:
            consume = 0.0
        pool -= consume
        residual = col - consume
        if residual <= 0.005:
            continue  # fully settled — not part of the pending picture
        stop = s["stop_at"]
        if oldest_date is None and stop is not None:
            oldest_date = stop
        wd = working_days_between(stop, today) if stop else 0
        status = "partially_confirmed" if consume > 0.005 else "unconfirmed"
        pending_rows.append({
            "session_id": s["session_id"],
            "session_name": s["session_name"],
            "branch_config": s["config"],
            "stop_at": stop.isoformat() if stop else None,
            "collected_amount": round(col, 2),
            "confirmed_amount": round(consume, 2),
            "residual_unconfirmed": round(residual, 2),
            "status": status,
            "working_days_since_stop_at": wd,
            "is_late": bool(wd > LATE_WORKING_DAYS),
        })
    # Oldest unconfirmed at the top (oldest stop_at first); None stop_at sinks to bottom.
    pending_rows.sort(key=lambda r: (r["stop_at"] is None, r["stop_at"] or ""))

    if is_manual:
        header_status = "manual"
    elif not pending_rows:
        header_status = "ok"
    elif oldest_date and working_days_between(oldest_date, today) > LATE_WORKING_DAYS:
        header_status = "late"
    else:
        header_status = "due_soon"

    header = {
        "collected": round(collected, 2),
        "confirmed": round(confirmed, 2),
        "commission": round(settled_total - confirmed, 2),
        "pending": round(balance, 2),
        "unconfirmed_sessions_count": len(pending_rows),
        "oldest_unconfirmed_stop_at": oldest_date.isoformat() if oldest_date else None,
        "oldest_unconfirmed_working_days": (
            working_days_between(oldest_date, today) if oldest_date else 0),
        "status": header_status,
        "manually_handled": is_manual,
    }

    # Recent Geidea settlement credits (63001-confirmation legs) — the batches that have
    # arrived for this branch, most recent first.
    conf_lines = [l for l in lines if (l.get("credit") or 0) > 0
                  and _m2o(l["move_id"])[0] in confirmation_moves]
    conf_lines.sort(key=lambda l: (l.get("date") or "", l["id"]), reverse=True)
    recent_confirmations = []
    for l in conf_lines[:RECENT_CONFIRMATIONS_LIMIT]:
        d = _parse_date(l.get("date"))
        recent_confirmations.append({
            "date": d.isoformat() if d else None,
            "amount": round(float(l.get("credit") or 0.0), 2),
            "ref": _m2o(l["move_id"])[1],
            "name": l.get("name") or "",
        })

    return {
        "as_of": now_utc.isoformat(),
        "company_id": company_id,
        "journal_id": journal_id,
        "branch": branch_name,
        "journal_code": jmeta["code"],
        "header": header,
        "sessions": pending_rows,
        "recent_confirmations": recent_confirmations,
    }
