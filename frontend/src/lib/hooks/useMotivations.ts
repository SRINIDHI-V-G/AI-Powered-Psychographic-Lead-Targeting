'use client';

import { useQuery } from '@tanstack/react-query';
import { getMotivations } from '../api/motivations';

export function useMotivations(productId: string) {
  return useQuery({
    queryKey: ['motivations', productId],
    queryFn: () => getMotivations(productId),
    enabled: Boolean(productId),
    staleTime: 30000,
  });
}
