"""POS Session Monitor — open/close discipline per branch (Area 1).

Answers: "Are POS sessions being closed regularly (2-3x/day) per branch, or are
sessions left open for days?"

100% READ-ONLY. Uses only `search_read` / `read` on the existing
OdooReadOnlyClient (the client hard-blocks every write method).

Query strategy: pos.session holds ~15k rows all-time, so a bounded, paginated
`search_read` over a date window is acceptable HERE. Do NOT copy this approach
to account.move.line work elsewhere (millions of rows) — there `read_group` is
mandatory.

Discovery caveat reused: `pos.session.company_id` is NOT SQL-groupable/filterable
("Cannot convert field pos.session.company_id to SQL"). We therefore attribute
every session to a company/branch via its `config_id` -> `pos.config` map, and we
never group or filter sessions by `company_id` directly (company filtering is
applied through the set of `pos.config` ids instead).

Filter scope: the DATE range applies to `by_branch` only (an open session may
predate it, so open_sessions/summary stay date-independent). The COMPANY filter,
by contrast, scopes ALL THREE blocks — open_sessions, summary AND by_branch —
because picking a company should narrow the whole screen to that company.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.models.pos import PosMonitorFilter

OPEN_STATES = ["opened", "closing_control"]

# Severity tiers, by how long a still-open session has been open (in days).
WARNING_AFTER_DAYS = 1.0   # >= 24h
CRITICAL_AFTER_DAYS = 7.0  # > one week

_OPEN_FIELDS = ["id", "name", "config_id", "user_id", "start_at",
                "order_count", "rescue", "state"]
_PERIOD_FIELDS = ["id", "config_id", "start_at", "stop_at", "state"]


def _parse_utc(value) -> datetime | None:
    """Parse a stored Odoo datetime ('YYYY-MM-DD HH:MM:SS', UTC) as tz-aware UTC.

    Returns None for empty / False / malformed values. Odoo stores datetimes in
    UTC, so durations computed against `datetime.now(timezone.utc)` are tz-safe.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _m2o(value) -> tuple:
    """Split an Odoo many2one [id, name] pair into (id, name)."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    return None, ""


def _severity(age_days: float) -> str:
    if age_days > CRITICAL_AFTER_DAYS:
        return "critical"
    if age_days >= WARNING_AFTER_DAYS:
        return "warning"
    return "ok"


def _fetch_all(client, model, domain, fields, *, order=None, batch=2000, hard_cap=50000):
    """Paginated search_read — the client default limit is 80, so page explicitly."""
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


def compute_pos_sessions(client, filters: PosMonitorFilter) -> dict:
    now_utc = datetime.now(timezone.utc)

    # by_branch period (the open_sessions block ignores this).
    date_from = filters.date_from or (now_utc.date() - timedelta(days=90))
    date_to = filters.date_to or now_utc.date()
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    # ── Active config map (one config is archived; query active only) ──────────
    active_configs = client.search_read(
        "pos.config",
        domain=[("active", "=", True)],
        fields=["id", "name", "company_id"],
        limit=300,
    )
    config_map: dict[int, dict] = {}
    for c in active_configs:
        comp_id, comp_name = _m2o(c.get("company_id"))
        config_map[c["id"]] = {
            "name": c.get("name") or "—",
            "company": comp_name,
            "company_id": comp_id,
        }

    # ── Block 1: open_sessions (LIVE — ignores the date filter) ────────────────
    open_raw = _fetch_all(
        client, "pos.session",
        domain=[("state", "in", OPEN_STATES)],
        fields=_OPEN_FIELDS, order="start_at asc",
    )

    # Resolve any archived configs referenced by open sessions. `read` by id
    # returns records regardless of the active flag (no search => active_test
    # does not apply), so this stays read-only and avoids touching session.company_id.
    missing = {cid for cid in (_m2o(s.get("config_id"))[0] for s in open_raw)
               if cid and cid not in config_map}
    if missing:
        for c in client.read("pos.config", list(missing), ["name", "company_id"]):
            comp_id, comp_name = _m2o(c.get("company_id"))
            config_map[c["id"]] = {
                "name": c.get("name") or "—",
                "company": comp_name,
                "company_id": comp_id,
            }

    # Company filter applies to open sessions too (unlike the date filter):
    # attribute each session to a company via its config_id -> config_map (company
    # is resolved there for active AND archived configs) and keep only the selected
    # company's sessions. config_id is the company key — pos.session.company_id is
    # never read/grouped directly (discovery caveat). This narrows open_sessions,
    # and therefore open_by_config and the summary, to the chosen company.
    if filters.company_id:
        open_raw = [
            s for s in open_raw
            if config_map.get(_m2o(s.get("config_id"))[0], {}).get("company_id")
            == filters.company_id
        ]

    open_sessions: list[dict] = []
    for s in open_raw:
        cfg_id, cfg_name = _m2o(s.get("config_id"))
        _, cashier = _m2o(s.get("user_id"))
        info = config_map.get(cfg_id, {})
        start = _parse_utc(s.get("start_at"))
        age_seconds = (now_utc - start).total_seconds() if start else 0.0
        age_days = age_seconds / 86400.0
        open_sessions.append({
            "session_id": s["id"],
            "name": s.get("name") or "—",
            "config_id": cfg_id,
            "branch": info.get("name") or cfg_name or "—",
            "company": info.get("company", ""),
            "cashier": cashier or "—",
            "start_at": s.get("start_at"),
            "age_hours": round(age_seconds / 3600.0, 1),
            "age_days": round(age_days, 1),
            "order_count": s.get("order_count") or 0,
            "rescue": bool(s.get("rescue")),
            "state": s.get("state"),
            "severity": _severity(age_days),
        })
    # Most stale first.
    open_sessions.sort(key=lambda x: x["age_days"], reverse=True)

    # Index live open sessions by config for the by_branch block.
    open_by_config: dict[int, list] = {}
    for o in open_sessions:
        open_by_config.setdefault(o["config_id"], []).append(o)

    # ── Block 2: by_branch (uses the date filter; per active config) ───────────
    branch_configs = list(active_configs)
    if filters.company_id:
        # Filter by config.company_id (a stored, groupable field) — never by the
        # session's own company_id (not SQL-convertible).
        branch_configs = [c for c in active_configs
                          if _m2o(c.get("company_id"))[0] == filters.company_id]
    branch_config_ids = [c["id"] for c in branch_configs]

    period_sessions: list[dict] = []
    if branch_config_ids:
        period_sessions = _fetch_all(
            client, "pos.session",
            domain=[
                ("config_id", "in", branch_config_ids),
                ("start_at", ">=", f"{date_from.isoformat()} 00:00:00"),
                ("start_at", "<=", f"{date_to.isoformat()} 23:59:59"),
            ],
            fields=_PERIOD_FIELDS, order="start_at asc",
        )

    # Aggregate per config in Python — duration needs stop_at - start_at, which
    # cannot be computed server-side.
    buckets: dict[int, dict] = {
        c["id"]: {"sessions_count": 0, "active_days": set(),
                  "durations": [], "long_sessions_count": 0}
        for c in branch_configs
    }
    for s in period_sessions:
        cid = _m2o(s.get("config_id"))[0]
        b = buckets.get(cid)
        if b is None:
            continue
        b["sessions_count"] += 1
        start = _parse_utc(s.get("start_at"))
        if start:
            b["active_days"].add(start.date())
        stop = _parse_utc(s.get("stop_at"))
        if start and stop:  # closed sessions only have a stop_at
            dur_h = (stop - start).total_seconds() / 3600.0
            if dur_h >= 0:
                b["durations"].append(dur_h)
                if dur_h > 24.0:
                    b["long_sessions_count"] += 1

    by_branch: list[dict] = []
    for c in branch_configs:
        cid = c["id"]
        b = buckets[cid]
        info = config_map.get(cid, {})
        opens = open_by_config.get(cid, [])
        open_now = len(opens)
        sessions_count = b["sessions_count"]
        # Skip dormant branches: no activity in period AND nothing open now.
        if sessions_count == 0 and open_now == 0:
            continue
        distinct_active_days = len(b["active_days"])
        durations = b["durations"]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        max_duration = max(durations) if durations else 0.0
        oldest_open = max((o["age_days"] for o in opens), default=0.0)
        has_critical = any(o["severity"] == "critical" for o in opens)
        discipline = "needs_attention" if (has_critical or avg_duration >= 24.0) else "good"
        by_branch.append({
            "config_id": cid,
            "branch": info.get("name") or c.get("name") or "—",
            "company": info.get("company", ""),
            "sessions_count": sessions_count,
            "distinct_active_days": distinct_active_days,
            "sessions_per_active_day": (round(sessions_count / distinct_active_days, 2)
                                        if distinct_active_days else 0.0),
            "avg_duration_hours": round(avg_duration, 1),
            "max_duration_hours": round(max_duration, 1),
            "long_sessions_count": b["long_sessions_count"],
            "open_now": open_now,
            "oldest_open_age_days": round(oldest_open, 1),
            "discipline": discipline,
        })
    by_branch.sort(key=lambda x: x["sessions_count"], reverse=True)

    # ── Block 3: summary ───────────────────────────────────────────────────────
    summary = {
        "open_now_total": len(open_sessions),
        "warning_count": sum(1 for o in open_sessions if o["severity"] == "warning"),
        "critical_count": sum(1 for o in open_sessions if o["severity"] == "critical"),
        "oldest_open_age_days": round(
            max((o["age_days"] for o in open_sessions), default=0.0), 1),
        "rescue_open_count": sum(1 for o in open_sessions if o["rescue"]),
        "active_branches": len(by_branch),
    }

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "as_of": now_utc.isoformat(),
        "open_sessions": open_sessions,
        "by_branch": by_branch,
        "summary": summary,
    }
