'use client';

import { useQuery } from '@tanstack/react-query';
import { getDashboardOverview } from '../api/dashboard';

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: getDashboardOverview,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}
