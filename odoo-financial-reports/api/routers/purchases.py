from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.common import ReportFilter
from api.services.purchases import compute_purchases

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/purchases")
def purchases(filters: ReportFilter, client=Depends(get_odoo_client)):
    cache_key = f"purchases:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_purchases(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
