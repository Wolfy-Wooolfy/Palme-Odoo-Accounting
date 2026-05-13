import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchCompanies, fetchDateRange, fetchSafetyStatus, fetchCacheStats, clearCache } from '../api/meta';
import toast from 'react-hot-toast';

const LONG_STALE = 10 * 60 * 1000; // 10 min

export const useCompanies = () =>
  useQuery({ queryKey: ['companies'], queryFn: fetchCompanies, staleTime: LONG_STALE });

export const useDateRange = () =>
  useQuery({ queryKey: ['date-range'], queryFn: fetchDateRange, staleTime: LONG_STALE });

export const useSafetyStatus = () =>
  useQuery({ queryKey: ['safety-status'], queryFn: fetchSafetyStatus, staleTime: LONG_STALE });

export const useCacheStats = () =>
  useQuery({ queryKey: ['cache-stats'], queryFn: fetchCacheStats, staleTime: 30_000 });

export const useClearCache = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: clearCache,
    onSuccess: (data) => {
      toast.success(`Cache cleared — ${data.cleared} entries removed`);
      qc.invalidateQueries({ queryKey: ['cache-stats'] });
    },
    onError: () => toast.error('Failed to clear cache'),
  });
};
