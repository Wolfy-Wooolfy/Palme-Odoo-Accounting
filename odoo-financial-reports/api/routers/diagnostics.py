from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_odoo_client
from api.models.common import AsOfFilter
from api.services.diagnostics import diagnose_balance_sheet

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.post("/balance-sheet")
def balance_sheet_diagnostic(filters: AsOfFilter, client=Depends(get_odoo_client)):
    try:
        return diagnose_balance_sheet(
            client,
            as_of=filters.date_to,
            company_id=filters.company_id,
            posted_only=filters.posted_only,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"Safety guard triggered: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
