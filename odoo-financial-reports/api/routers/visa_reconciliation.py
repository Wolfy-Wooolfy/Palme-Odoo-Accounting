from fastapi import APIRouter, Depends, HTTPException

from api.cache.sqlite_cache import get_cache
from api.config import settings
from api.deps import get_odoo_client
from api.models.visa import VisaBranchDetailFilter, VisaReconFilter
from api.services.visa_reconciliation import (
    compute_visa_branch_detail,
    compute_visa_reconciliation,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# Concurrency note: like every other report this endpoint issues many sequential
# read-only Odoo calls and uses the shared singleton client. The OdooReadOnlyClient
# serialises every RPC dispatch with an internal lock, so the shared, non-thread-safe
# XML-RPC socket is safe under uvicorn's threadpool — no dedicated connection needed.


@router.post("/visa-reconciliation")
def visa_reconciliation(filters: VisaReconFilter, client=Depends(get_odoo_client)):
    # Cache-key version: bump when the response SHAPE or SEMANTICS change so stale
    # entries from an older build are never served past their TTL. v2 = company_id now
    # scopes the whole report (was hardcoded co3) + added is_default_company.
    cache_key = f"visa_reconciliation:v2:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_visa_reconciliation(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}


@router.post("/visa-reconciliation/branch-detail")
def visa_reconciliation_branch_detail(
    filters: VisaBranchDetailFilter, client=Depends(get_odoo_client)
):
    # Session-level drill-down for ONE branch journal: the sessions that make up that
    # branch's pending holding balance (Σ residual_unconfirmed == the branch's pending
    # on the main screen). Read-only; same shared client / serialised-RPC pattern.
    cache_key = f"visa_branch_detail:v1:{filters.model_dump_json()}"

    if settings.cache_enabled:
        cache = get_cache(settings.cache_db_path, settings.cache_ttl_seconds)
        cached = cache.get(cache_key)
        if cached:
            return {"cached": True, **cached}

    try:
        data = compute_visa_branch_detail(client, filters)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if settings.cache_enabled:
        cache.set(cache_key, data)

    return {"cached": False, **data}
