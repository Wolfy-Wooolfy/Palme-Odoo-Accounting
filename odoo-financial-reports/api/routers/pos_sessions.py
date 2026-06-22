import threading

from fastapi import APIRouter, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_audit_logger
from api.models.pos import PosMonitorFilter
from api.services.pos_sessions import compute_pos_sessions
from src.odoo_client import OdooReadOnlyClient

router = APIRouter(prefix="/reports", tags=["reports"])

# ── Dedicated, isolated Odoo connection for this endpoint ─────────────────────
# The POS monitor issues MANY sequential read-only Odoo calls (active-config map +
# paginated open-session and period-session fetches). The shared singleton
# `get_odoo_client` wraps ONE persistent, NON-thread-safe `xmlrpc.client.ServerProxy`
# connection. Because uvicorn runs sync endpoints in a threadpool, this long
# call-sequence overlapped with other requests on that single socket — e.g. the
# FilterPanel's GET /companies fired at the same instant the POS page mounts — and
# concurrent use of one xmlrpc connection raises `http.client.CannotSendRequest`
# ("Request-sent"), surfacing as a bodiless HTTP 500 (no `detail`, hence the generic
# "Request failed with status code 500" in the UI). Verified via the traceback in
# api_err.log and a concurrency burst (12/28 requests 500'd).
#
# Fix: give this endpoint its OWN read-only client (a separate connection) and
# serialise access to it with a lock, so its calls can neither corrupt nor race the
# shared connection that the rest of the dashboard relies on. Additive only — the
# shared client, the Odoo client class, other endpoints and the safety code are
# all untouched; this client is just as read-only (same 7-layer guarded class).
_pos_client = None  # OdooReadOnlyClient, created lazily on first request
_pos_client_lock = threading.Lock()


def _get_pos_client() -> OdooReadOnlyClient:
    global _pos_client
    if _pos_client is None:
        _pos_client = OdooReadOnlyClient(audit_logger=get_audit_logger())
    return _pos_client


@router.post("/pos-sessions")
def pos_sessions(filters: PosMonitorFilter):
    # Cache-key version: bump when the response SHAPE changes so stale entries from
    # an older build are never served. v2 = company filter scopes open_sessions/summary
    # too (not just by_branch); a pre-fix v1 entry would otherwise serve unscoped
    # open_sessions for a single-company request until its 30-min TTL expired.
    cache_key = f"pos_sessions:v2:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        # One in-flight POS query at a time on the dedicated connection — the lock
        # makes concurrent POS requests serialise instead of colliding on the socket.
        with _pos_client_lock:
            data = compute_pos_sessions(_get_pos_client(), filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
