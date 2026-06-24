import { useQuery } from '@tanstack/react-query';
import {
  fetchTrialBalance, fetchProfitLoss, fetchBalanceSheet,
  fetchDiagnostic, fetchCustomerAging, fetchVendorAging,
  fetchCashBank, fetchGeneralLedger, fetchSales, fetchPurchases,
  fetchPosSessions, fetchVisaReconciliation, fetchVisaBranchDetail,
  fetchBankMovements, fetchBankGapDetail,
} from '../api/reports';

const STALE = 5 * 60 * 1000; // 5 min

export const useTrialBalance = (filters, options = {}) =>
  useQuery({
    queryKey: ['trial-balance', filters],
    queryFn: () => fetchTrialBalance(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useProfitLoss = (filters, options = {}) =>
  useQuery({
    queryKey: ['profit-loss', filters],
    queryFn: () => fetchProfitLoss(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useBalanceSheet = (filters, options = {}) =>
  useQuery({
    queryKey: ['balance-sheet', filters],
    queryFn: () => fetchBalanceSheet(filters),
    enabled: !!(filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useDiagnostic = (filters, options = {}) =>
  useQuery({
    queryKey: ['diagnostic', filters],
    queryFn: () => fetchDiagnostic(filters),
    enabled: !!(filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useCustomerAging = (filters, options = {}) =>
  useQuery({
    queryKey: ['customer-aging', filters],
    queryFn: () => fetchCustomerAging(filters),
    enabled: !!(filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useVendorAging = (filters, options = {}) =>
  useQuery({
    queryKey: ['vendor-aging', filters],
    queryFn: () => fetchVendorAging(filters),
    enabled: !!(filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useCashBank = (filters, options = {}) =>
  useQuery({
    queryKey: ['cash-bank', filters],
    queryFn: () => fetchCashBank(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useGeneralLedger = (glFilter, options = {}) =>
  useQuery({
    queryKey: ['general-ledger', glFilter],
    queryFn: () => fetchGeneralLedger(glFilter),
    enabled: !!(glFilter?.account_id && glFilter?.date_from && glFilter?.date_to),
    staleTime: 60 * 1000, // 1 min — GL is more volatile
    ...options,
  });

export const useSales = (filters, options = {}) =>
  useQuery({
    queryKey: ['sales', filters],
    queryFn: () => fetchSales(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const usePurchases = (filters, options = {}) =>
  useQuery({
    queryKey: ['purchases', filters],
    queryFn: () => fetchPurchases(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const usePosSessions = (filters, options = {}) =>
  useQuery({
    queryKey: ['pos-sessions', filters],
    queryFn: () => fetchPosSessions(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

export const useVisaReconciliation = (filters, options = {}) =>
  useQuery({
    queryKey: ['visa-reconciliation', filters],
    queryFn: () => fetchVisaReconciliation(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

// Lazy session-level drill-down for one branch — only fires once a branch is opened
// (company_id + journal_id both present). Dates are ignored server-side (full-history
// "as of today"), so they are not part of the enable gate.
export const useVisaBranchDetail = (filters, options = {}) =>
  useQuery({
    queryKey: ['visa-branch-detail', filters],
    queryFn: () => fetchVisaBranchDetail(filters),
    enabled: !!(filters?.company_id && filters?.journal_id),
    staleTime: STALE,
    ...options,
  });

// Bank Movements & Gaps (Area 3). filters carries the standard date/company filter
// PLUS gaps_only / offset / limit — all part of the query key so the gaps-only toggle
// and pagination refetch. Dates only drive movement VOLUME (gaps are full-history), so
// the gate matches the other date-driven reports.
export const useBankMovements = (filters, options = {}) =>
  useQuery({
    queryKey: ['bank-movements', filters],
    queryFn: () => fetchBankMovements(filters),
    enabled: !!(filters?.date_from && filters?.date_to),
    staleTime: STALE,
    ...options,
  });

// Lazy per-bank GAP drill-down — only fires once a bank row's gap is opened
// (journal_id present). Dates are ignored server-side (the gap is full-history "as of
// today"), so they are not part of the enable gate; company_id + offset/limit are.
export const useBankGapDetail = (filters, options = {}) =>
  useQuery({
    queryKey: ['bank-gap-detail', filters],
    queryFn: () => fetchBankGapDetail(filters),
    enabled: !!filters?.journal_id,
    staleTime: STALE,
    ...options,
  });
