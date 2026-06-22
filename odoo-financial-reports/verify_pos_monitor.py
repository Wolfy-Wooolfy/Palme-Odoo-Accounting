"""Verification harness for the POS Session Monitor (Phase 3A).

Two layers, because the original harness only tested the service function and so
missed an HTTP-only failure (a shared XML-RPC connection raising CannotSendRequest
under concurrency -> HTTP 500):

  A. SERVICE  — calls compute_pos_sessions(...) directly against live Odoo.
  B. HTTP     — drives the REAL endpoint over HTTP, including a concurrency burst
                (pos-sessions racing GET /companies, the exact POS-page mount) that
                guards against the CannotSendRequest regression. Skipped (not failed)
                if no server is reachable.

Read-only; writes nothing to Odoo. Re-runnable.

Run from odoo-financial-reports/ :
    PYTHONIOENCODING=utf-8 python verify_pos_monitor.py
Point the HTTP layer at a running server with:
    POS_MONITOR_BASE_URL=http://127.0.0.1:8000   (default)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from api.models.pos import PosMonitorFilter
from api.services.pos_sessions import compute_pos_sessions
from src.odoo_client import OdooReadOnlyClient

BASE_URL = os.environ.get("POS_MONITOR_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = BASE_URL + "/api/v1"
JAN_2026 = {"date_from": "2026-01-01", "date_to": "2026-01-31", "company_id": None, "posted_only": True}


# ── Layer A: service function ────────────────────────────────────────────────
def service_check() -> None:
    print("=== A. SERVICE (compute_pos_sessions directly) ===")
    client = OdooReadOnlyClient()
    flt = PosMonitorFilter(
        date_from=date.today() - timedelta(days=730),
        date_to=date.today(),
        company_id=None,
    )
    data = compute_pos_sessions(client, flt)

    s = data["summary"]
    for k, v in s.items():
        print(f"  {k}: {v}")
    opens = data["open_sessions"]
    print("  Top 3 oldest open:")
    for o in opens[:3]:
        print(f"    {o['name']:<14} {o['branch'][:24]:<24} age={o['age_days']:>7.1f}d "
              f"orders={o['order_count']:>5} rescue={str(o['rescue']):<5} sev={o['severity']}")
    bb = data["by_branch"]
    companies = sorted({b["company"] for b in bb if b["company"]})
    print(f"  by_branch rows: {len(bb)} across {len(companies)} companies: {companies}")
    print(f"  CHECK open_now_total>0: {s['open_now_total'] > 0} ({s['open_now_total']}, ~29 baseline)")
    print(f"  CHECK 3 companies     : {len(companies) == 3}")


# ── Layer B: real HTTP endpoint ──────────────────────────────────────────────
def _http(method: str, path: str, body=None, timeout: int = 180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode()


def http_check() -> None:
    print(f"\n=== B. HTTP ({API}) ===")
    st, _ = _http("GET", "/health", timeout=5)
    if st != 200:
        print(f"  SKIPPED — no server reachable (status={st}). "
              f"Start uvicorn or set POS_MONITOR_BASE_URL.")
        return

    # 1. Jan-2026 (the reported failing payload)
    st1, b1 = _http("POST", "/reports/pos-sessions", JAN_2026)
    d1 = json.loads(b1) if st1 == 200 else {}
    comps = sorted({b["company"] for b in d1.get("by_branch", []) if b["company"]})
    print(f"  [1] Jan-2026 POST      : HTTP {st1} | open_now_total="
          f"{d1.get('summary', {}).get('open_now_total')} | by_branch={len(d1.get('by_branch', []))} "
          f"| companies={len(comps)} {comps}")

    # 2. Default dates (no date_from/date_to -> service defaults to last 90 days)
    st2, b2 = _http("POST", "/reports/pos-sessions", {"company_id": None, "posted_only": True})
    d2 = json.loads(b2) if st2 == 200 else {}
    print(f"  [2] default-dates POST : HTTP {st2} | period={d2.get('period')} "
          f"| open_now_total={d2.get('summary', {}).get('open_now_total')}")

    # 3. Company scoping — selecting a company must narrow ALL THREE blocks
    #    (summary, open_sessions AND by_branch). Previously untested: every prior
    #    request sent company_id=null, so the open_sessions/summary leak was hidden.
    st_c, b_c = _http("GET", "/companies")
    comp_list = json.loads(b_c) if st_c == 200 else []
    comp_ids = [(c["id"], c["name"]) for c in comp_list][:3]

    def _scope(payload):
        st, b = _http("POST", "/reports/pos-sessions", payload)
        d = json.loads(b) if st == 200 else {}
        opens = d.get("open_sessions", [])
        return {
            "http": st,
            "open_now": d.get("summary", {}).get("open_now_total"),
            "open_rows": len(opens),
            "open_companies": sorted({o.get("company") for o in opens if o.get("company")}),
            "branch_companies": sorted({x["company"] for x in d.get("by_branch", []) if x["company"]}),
        }

    base = _scope({"company_id": None})
    print("  [3] company scoping  (open_now | open_rows | open_companies | branch_companies):")
    print(f"        all (null)          : {str(base['open_now']):>3} | {base['open_rows']:>3} | "
          f"{base['open_companies']} | {base['branch_companies']}")
    per_company_sum, scope_ok = 0, True
    for cid, cname in comp_ids:
        r = _scope({"company_id": cid})
        per_company_sum += (r["open_now"] or 0)
        present = set(r["open_companies"]) | set(r["branch_companies"])
        single = present.issubset({cname})           # only this company (or empty)
        monotonic = (r["open_now"] or 0) <= (base["open_now"] or 0)
        scope_ok = scope_ok and r["http"] == 200 and single and monotonic
        print(f"        #{cid} {cname[:18]:<18}: {str(r['open_now']):>3} | {r['open_rows']:>3} | "
              f"{r['open_companies']} | {r['branch_companies']}  [{'OK' if single else 'LEAK!'}]")
    sums_match = per_company_sum == (base["open_now"] or 0)
    print(f"        sum(per-company open_now)={per_company_sum} vs all={base['open_now']} "
          f"-> {'match' if sums_match else 'differ'}")
    print(f"        company scoping: {'PASS' if scope_ok else 'FAIL'}"
          f"{'' if sums_match else ' (note: per-company sum != all total)'}")

    # 4. Concurrency burst — regression guard for the CannotSendRequest 500.
    #    Mirrors the POS page mount: pos-sessions racing GET /companies.
    statuses = []
    for _ in range(5):
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(_http, "POST", "/reports/pos-sessions", JAN_2026) for _ in range(3)]
            futs.append(ex.submit(_http, "GET", "/companies"))
            statuses += [f.result()[0] for f in futs]
    bad = [x for x in statuses if x != 200]
    print(f"  [4] concurrency burst  : {len(statuses)} reqs, non-200={len(bad)} "
          f"-> {'PASS' if not bad else 'FAIL ' + str(bad)}")

    ok = st1 == 200 and st2 == 200 and len(comps) == 3 and scope_ok and not bad
    print(f"  HTTP OVERALL: {'PASS' if ok else 'FAIL'}")


def main() -> None:
    service_check()
    http_check()


if __name__ == "__main__":
    main()
