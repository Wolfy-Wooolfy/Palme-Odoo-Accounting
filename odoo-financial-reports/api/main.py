from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.deps import get_audit_logger, get_odoo_client
from api.routers import (
    aging,
    balance_sheet,
    cash_bank,
    diagnostics,
    general_ledger,
    meta,
    profit_loss,
    purchases,
    sales,
    trial_balance,
)
from src.odoo_client import OdooReadOnlyClient
from src.utils.safety_test import run_safety_self_test


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Running pre-flight safety self-test...")
    test_client = OdooReadOnlyClient(skip_connect=True)
    run_safety_self_test(test_client)
    print("Safety self-test passed — all 5 write guards verified")

    print("Connecting to Odoo...")
    client = get_odoo_client()
    version = client.version_info.get("server_version", "unknown")
    print(f"Connected: Odoo {version} | DB: {client.db} | uid: {client.uid}")

    yield

    audit = get_audit_logger()
    audit.write_safety_report()
    print("Shutdown complete — SAFETY_REPORT.md written")


app = FastAPI(
    title="Odoo Financial Reports API",
    description="READ-ONLY financial reporting from Odoo 17 Enterprise",
    version="2C.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Core financial reports
app.include_router(meta.router, prefix="/api/v1")
app.include_router(trial_balance.router, prefix="/api/v1")
app.include_router(profit_loss.router, prefix="/api/v1")
app.include_router(balance_sheet.router, prefix="/api/v1")

# Phase 2C — new reports
app.include_router(diagnostics.router, prefix="/api/v1")
app.include_router(aging.router, prefix="/api/v1")
app.include_router(cash_bank.router, prefix="/api/v1")
app.include_router(general_ledger.router, prefix="/api/v1")
app.include_router(sales.router, prefix="/api/v1")
app.include_router(purchases.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
