'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getProducts,
  getProduct,
  getProductStatus,
  createProduct,
  restartProduct,
  regenerateMotivations,
} from '../api/products';
import type { ProductCreateInput } from '../types/api';
import { isRunning } from '../utils';

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: getProducts,
    staleTime: 5000,
  });
}

export function useProduct(id: string) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => getProduct(id),
    enabled: Boolean(id),
    staleTime: 5000,
  });
}

export function useProductStatus(id: string, enabled = true) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ['product-status', id],
    queryFn: async () => {
      const status = await getProductStatus(id);
      if (status.status === 'ranked' || status.status === 'failed') {
        // Invalidate product details when done
        void qc.invalidateQueries({ queryKey: ['product', id] });
      }
      return status;
    },
    enabled: Boolean(id) && enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3000;
      return isRunning(data.status) ? 3000 : false;
    },
    staleTime: 2000,
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProductCreateInput) => createProduct(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['products'] });
    },
  });
}

export function useRestartProduct(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => restartProduct(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['product-status', id] });
      void qc.invalidateQueries({ queryKey: ['product', id] });
    },
  });
}

export function useRegenerateMotivations(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => regenerateMotivations(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['product-status', id] });
      void qc.invalidateQueries({ queryKey: ['motivations', id] });
    },
  });
}
