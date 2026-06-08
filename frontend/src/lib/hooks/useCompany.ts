'use client';

import { useQuery } from '@tanstack/react-query';
import { getMyCompany } from '../api/companies';

export function useCompany() {
  return useQuery({
    queryKey: ['company-me'],
    queryFn: getMyCompany,
    staleTime: 60000,
  });
}
