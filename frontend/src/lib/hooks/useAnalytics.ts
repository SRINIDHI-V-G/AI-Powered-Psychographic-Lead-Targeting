'use client';

import { useQuery } from '@tanstack/react-query';
import { getLeadsSummary, getLeadsAnalytics } from '../api/validation';

export function useLeadsSummary(productId: string) {
  return useQuery({
    queryKey: ['leads-summary', productId],
    queryFn: () => getLeadsSummary(productId),
    enabled: Boolean(productId),
    staleTime: 30000,
  });
}

export function useLeadsAnalytics(productId: string) {
  return useQuery({
    queryKey: ['leads-analytics', productId],
    queryFn: () => getLeadsAnalytics(productId),
    enabled: Boolean(productId),
    staleTime: 30000,
  });
}
