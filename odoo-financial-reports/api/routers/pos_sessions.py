from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.pos import PosMonitorFilter
from api.services.pos_sessions import compute_pos_sessions

router = APIRouter(prefix="/reports", tags=["reports"])

# Concurrency note: this endpoint issues MANY sequential read-only Odoo calls. It used
# to keep its own dedicated connection + lock to avoid colliding with other requests on
# the shared, non-thread-safe XML-RPC socket. That race is now fixed centrally — the
# OdooReadOnlyClient serialises every RPC dispatch with an internal lock — so this
# endpoint safely uses the shared singleton client like every other report (no more
# duplicated workaround, no second prod connection).


@router.post("/pos-sessions")
def pos_sessions(filters: PosMonitorFilter, client=Depends(get_odoo_client)):
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
        data = compute_pos_sessions(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
