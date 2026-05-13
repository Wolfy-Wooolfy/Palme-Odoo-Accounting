from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.common import AsOfFilter
from api.services.aging import compute_aging

router = APIRouter(prefix="/reports", tags=["reports"])

RECEIVABLE_TYPES = ["asset_receivable"]
PAYABLE_TYPES = ["liability_payable"]


@router.post("/customer-aging")
def customer_aging(filters: AsOfFilter, client=Depends(get_odoo_client)):
    cache_key = f"customer_aging:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_aging(
            client,
            account_types=RECEIVABLE_TYPES,
            as_of=filters.date_to,
            company_id=filters.company_id,
            posted_only=filters.posted_only,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}


@router.post("/vendor-aging")
def vendor_aging(filters: AsOfFilter, client=Depends(get_odoo_client)):
    cache_key = f"vendor_aging:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_aging(
            client,
            account_types=PAYABLE_TYPES,
            as_of=filters.date_to,
            company_id=filters.company_id,
            posted_only=filters.posted_only,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
