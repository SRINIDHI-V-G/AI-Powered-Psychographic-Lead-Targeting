'use client';

import { useQuery } from '@tanstack/react-query';
import { getNlpStatus } from '../api/nlp';

export function useNlpStatus(productId: string) {
  return useQuery({
    queryKey: ['nlp-status', productId],
    queryFn: () => getNlpStatus(productId),
    enabled: Boolean(productId),
    staleTime: 10000,
    refetchInterval: 5000,
  });
}
