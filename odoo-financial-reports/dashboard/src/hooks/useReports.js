import { useQuery } from '@tanstack/react-query';
import {
  fetchTrialBalance, fetchProfitLoss, fetchBalanceSheet,
  fetchDiagnostic, fetchCustomerAging, fetchVendorAging,
  fetchCashBank, fetchGeneralLedger, fetchSales, fetchPurchases,
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
