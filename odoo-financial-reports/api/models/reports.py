from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class TrialBalanceRow(BaseModel):
    account_id: int
    code: str
    name: str
    account_type: str
    debit: float
    credit: float
    balance: float


class TrialBalanceTotals(BaseModel):
    debit: float
    credit: float
    balance: float


class TrialBalanceResponse(BaseModel):
    cached: bool
    filters: dict[str, Any]
    rows: list[TrialBalanceRow]
    totals: TrialBalanceTotals
    row_count: int


class PLAccount(BaseModel):
    account_id: int
    code: str
    name: str
    balance: float
    amount: float


class PLSection(BaseModel):
    accounts: list[PLAccount]
    total: float


class PLResponse(BaseModel):
    cached: bool
    period: dict[str, str]
    revenue: PLSection
    expenses: PLSection
    net_profit: float


class BSAccount(BaseModel):
    account_id: int
    code: str
    name: str
    account_type: str
    balance: float


class BSSection(BaseModel):
    accounts: list[BSAccount]
    total: float


class BSResponse(BaseModel):
    cached: bool
    as_of: str
    assets: BSSection
    liabilities: BSSection
    equity: BSSection
    total_liabilities_and_equity: float
