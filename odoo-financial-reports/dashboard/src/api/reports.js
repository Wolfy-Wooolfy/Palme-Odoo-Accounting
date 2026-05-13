import client from './client';

// Ensures company_id is always null|integer and posted_only is always boolean
// before any payload reaches the backend. Guards against stale/invalid state.
function norm(filters) {
  const { company_id, posted_only, ...rest } = filters ?? {};
  return {
    ...rest,
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

export const searchAccounts = (q = '', limit = 50) =>
  client.get('/accounts/search', { params: { q, limit } }).then((r) => r.data);
