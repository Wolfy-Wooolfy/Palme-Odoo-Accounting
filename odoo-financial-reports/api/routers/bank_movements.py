from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.bank import BankGapDetailFilter, BankMovementsFilter
from api.services.bank_movements import compute_bank_gap_detail, compute_bank_movements

router = APIRouter(prefix="/reports", tags=["reports"])

# Concurrency note: like every other report this endpoint issues many sequential
# read-only Odoo calls and uses the shared singleton client. The OdooReadOnlyClient
# serialises every RPC dispatch with an internal lock, so the shared, non-thread-safe
# XML-RPC socket is safe under uvicorn's threadpool — no dedicated connection needed.


@router.post("/bank-movements")
def bank_movements(filters: BankMovementsFilter, client=Depends(get_odoo_client)):
    # Cache-key version: bump when the response SHAPE or SEMANTICS change so stale
    # entries from an older build are never served past their TTL.
    cache_key = f"bank_movements:v1:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_bank_movements(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}


@router.post("/bank-movements/gap-detail")
def bank_movements_gap_detail(
    filters: BankGapDetailFilter, client=Depends(get_odoo_client)
):
    # Per-bank GAP drill-down for ONE journal: the unreconciled account.payment movements
    # that make up that journal's gap (oldest-first). The header gap_count/gap_amount tie
    # EXACTLY to that journal's row on the main by_bank table for the same scope. Read-only;
    # same shared client / serialised-RPC pattern as every other report.
    cache_key = f"bank_gap_detail:v1:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_bank_gap_detail(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
