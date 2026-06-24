import client from './client';

// Normalises every payload before it hits the backend:
//  - Swaps date_from/date_to when reversed (PeriodFilter validator rejects date_to < date_from → 422)
//  - Coerces company_id to null|integer (never "")
//  - Ensures posted_only is boolean
function norm(filters) {
  if (!filters) return {};
  const { company_id, posted_only, date_from: df, date_to: dt, ...rest } = filters;
  let date_from = df, date_to = dt;
  if (date_from && date_to && date_from > date_to) [date_from, date_to] = [date_to, date_from];
  return {
    ...rest,
    date_from,
    date_to,
    company_id:
      company_id != null && company_id !== '' && !Number.isNaN(+company_id) && +company_id > 0
        ? +company_id
        : null,
    posted_only: typeof posted_only === 'boolean' ? posted_only : true,
  };
}

export const fetchTrialBalance = (filters) =>
  client.post('/reports/trial-balance', norm(filters)).then((r) => r.data);

export const fetchProfitLoss = (filters) =>
  client.post('/reports/profit-loss', norm(filters)).then((r) => r.data);

export const fetchBalanceSheet = (filters) =>
  client.post('/reports/balance-sheet', norm(filters)).then((r) => r.data);

export const fetchDiagnostic = (filters) =>
  client.post('/diagnostics/balance-sheet', norm(filters)).then((r) => r.data);

export const fetchCustomerAging = (filters) =>
  client.post('/reports/customer-aging', norm(filters)).then((r) => r.data);

export const fetchVendorAging = (filters) =>
  client.post('/reports/vendor-aging', norm(filters)).then((r) => r.data);

export const fetchCashBank = (filters) =>
  client.post('/reports/cash-bank', norm(filters)).then((r) => r.data);

export const fetchGeneralLedger = (glFilter) =>
  client.post('/reports/general-ledger', norm(glFilter)).then((r) => r.data);

export const fetchSales = (filters) =>
  client.post('/reports/sales', norm(filters)).then((r) => r.data);

export const fetchPurchases = (filters) =>
  client.post('/reports/purchases', norm(filters)).then((r) => r.data);

export const fetchPosSessions = (filters) =>
  client.post('/reports/pos-sessions', norm(filters)).then((r) => r.data);

export const fetchVisaReconciliation = (filters) =>
  client.post('/reports/visa-reconciliation', norm(filters)).then((r) => r.data);

export const fetchVisaBranchDetail = (filters) =>
  client.post('/reports/visa-reconciliation/branch-detail', norm(filters)).then((r) => r.data);

export const fetchBankMovements = (filters) =>
  client.post('/reports/bank-movements', norm(filters)).then((r) => r.data);

export const fetchBankGapDetail = (filters) =>
  client.post('/reports/bank-movements/gap-detail', norm(filters)).then((r) => r.data);

export const searchAccounts = (q = '', limit = 50) =>
  client.get('/accounts/search', { params: { q, limit } }).then((r) => r.data);
