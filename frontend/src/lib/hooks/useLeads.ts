'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getLeads, getLeadDetail, getMatchStatus, triggerMatch } from '../api/matching';

export function useLeads(
  productId: string,
  params: {
    page?: number;
    page_size?: number;
    min_score?: number;
    min_confidence?: number;
    sort?: 'top' | 'bottom';
  } = {}
) {
  return useQuery({
    queryKey: ['leads', productId, params],
    queryFn: () => getLeads(productId, params),
    enabled: Boolean(productId),
    staleTime: 10000,
  });
}

export function useLeadDetail(productId: string, userId: string) {
  return useQuery({
    queryKey: ['lead-detail', productId, userId],
    queryFn: () => getLeadDetail(productId, userId),
    enabled: Boolean(productId) && Boolean(userId),
    staleTime: 30000,
  });
}

export function useMatchStatus(productId: string) {
  return useQuery({
    queryKey: ['match-status', productId],
    queryFn: () => getMatchStatus(productId),
    enabled: Boolean(productId),
    staleTime: 5000,
  });
}

export function useTriggerMatch(productId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => triggerMatch(productId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['leads', productId] });
      void qc.invalidateQueries({ queryKey: ['match-status', productId] });
    },
  });
}
