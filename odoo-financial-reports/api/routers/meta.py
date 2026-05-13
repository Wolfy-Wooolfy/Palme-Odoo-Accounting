from fastapi import APIRouter, Depends

from api.deps import get_odoo_client
from src.odoo_client import ALLOWED_METHODS, FORBIDDEN_METHODS

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok", "read_only": True}


@router.get("/companies")
def companies(client=Depends(get_odoo_client)):
    return client.search_read(
        "res.company",
        fields=["id", "name", "currency_id"],
        limit=100,
    )


@router.get("/date-range")
def date_range(client=Depends(get_odoo_client)):
    oldest = client.search_read(
        "account.move",
        domain=[("state", "=", "posted")],
        fields=["date"],
        limit=1,
        order="date asc",
    )
    newest = client.search_read(
        "account.move",
        domain=[("state", "=", "posted")],
        fields=["date"],
        limit=1,
        order="date desc",
    )
    return {
        "min_date": oldest[0]["date"] if oldest else None,
        "max_date": newest[0]["date"] if newest else None,
    }


@router.get("/safety-status")
def safety_status():
    return {
        "read_only": True,
        "safety_layers_active": 7,
        "allowed_methods": sorted(ALLOWED_METHODS),
        "blocked_methods": sorted(FORBIDDEN_METHODS),
    }
