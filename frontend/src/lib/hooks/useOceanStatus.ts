'use client';

import { useQuery } from '@tanstack/react-query';
import { getOceanStatus } from '../api/ocean';

export function useOceanStatus(productId: string) {
  return useQuery({
    queryKey: ['ocean-status', productId],
    queryFn: () => getOceanStatus(productId),
    enabled: Boolean(productId),
    staleTime: 10000,
    refetchInterval: 5000,
  });
}
