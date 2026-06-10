'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDiscoveryJobs,
  getDiscoveredUsers,
  getPlatformStats,
  getUserContent,
  startDiscovery,
  getProviderStatus,
} from '../api/discovery';
import { getUserNlp } from '../api/nlp';
import { getUserOcean } from '../api/ocean';

export function useProviderStatus() {
  return useQuery({
    queryKey: ['provider-status'],
    queryFn: getProviderStatus,
    staleTime: 30000,
  });
}

export function useDiscoveryJobs(productId: string) {
  return useQuery({
    queryKey: ['discovery-jobs', productId],
    queryFn: () => getDiscoveryJobs(productId),
    enabled: Boolean(productId),
    refetchInterval: 5000,
    staleTime: 3000,
  });
}

export function useDiscoveredUsers(
  productId: string,
  params: { page?: number; limit?: number; job_id?: string } = {}
) {
  return useQuery({
    queryKey: ['discovered-users', productId, params],
    queryFn: () => getDiscoveredUsers(productId, params),
    enabled: Boolean(productId),
    staleTime: 10000,
  });
}

export function useUserContent(productId: string, userId: string) {
  return useQuery({
    queryKey: ['user-content', productId, userId],
    queryFn: () => getUserContent(productId, userId),
    enabled: Boolean(productId) && Boolean(userId),
    staleTime: 60000,
  });
}

export function useUserNlp(productId: string, userId: string) {
  return useQuery({
    queryKey: ['user-nlp', productId, userId],
    queryFn: () => getUserNlp(productId, userId),
    enabled: Boolean(productId) && Boolean(userId),
    staleTime: 60000,
  });
}

export function useUserOcean(productId: string, userId: string) {
  return useQuery({
    queryKey: ['user-ocean', productId, userId],
    queryFn: () => getUserOcean(productId, userId),
    enabled: Boolean(productId) && Boolean(userId),
    staleTime: 60000,
  });
}

export function usePlatformStats(productId: string) {
  return useQuery({
    queryKey: ['platform-stats', productId],
    queryFn: () => getPlatformStats(productId),
    enabled: Boolean(productId),
    staleTime: 10000,
  });
}

export function useStartDiscovery(productId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (maxUsers: number) => startDiscovery(productId, maxUsers),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['discovery-jobs', productId] });
    },
  });
}
