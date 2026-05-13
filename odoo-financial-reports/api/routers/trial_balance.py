from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.common import ReportFilter
from api.services.trial_balance import compute_trial_balance

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/trial-balance")
def trial_balance(filters: ReportFilter, client=Depends(get_odoo_client)):
    cache_key = f"trial_balance:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        rows = compute_trial_balance(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    result = {
        "filters": filters.model_dump(mode="json"),
        "rows": rows,
        "totals": {
            "debit": round(sum(r["debit"] for r in rows), 2),
            "credit": round(sum(r["credit"] for r in rows), 2),
            "balance": round(sum(r["balance"] for r in rows), 2),
        },
        "row_count": len(rows),
    }

    if settings.cache_enabled:
        cache.set(cache_key, result)

    return {"cached": False, **result}
