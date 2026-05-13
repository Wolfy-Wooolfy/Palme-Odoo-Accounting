from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_odoo_client
from api.models.common import GLFilter
from api.services.general_ledger import compute_general_ledger

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/general-ledger")
def general_ledger(gl_filter: GLFilter, client=Depends(get_odoo_client)):
    # General Ledger is NOT cached — it changes with every new transaction
    # and pagination offsets make caching complex.
    try:
        return compute_general_ledger(client, gl_filter)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
