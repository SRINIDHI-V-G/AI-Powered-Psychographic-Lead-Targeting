import apiClient from './client';
import type { Product, ProductStatusResponse, ProductCreateInput } from '../types/api';

export async function getProducts(): Promise<Product[]> {
  const { data } = await apiClient.get<Product[]>('/products');
  return data;
}

export async function getProduct(id: string): Promise<Product> {
  const { data } = await apiClient.get<Product>(`/products/${id}`);
  return data;
}

export async function getProductStatus(id: string): Promise<ProductStatusResponse> {
  const { data } = await apiClient.get<ProductStatusResponse>(`/products/${id}/status`);
  return data;
}

export async function createProduct(input: ProductCreateInput): Promise<Product> {
  const { data } = await apiClient.post<Product>('/products', input);
  return data;
}

export async function restartProduct(id: string): Promise<ProductStatusResponse> {
  const { data } = await apiClient.post<ProductStatusResponse>(`/products/${id}/restart`);
  return data;
}

export async function regenerateMotivations(id: string): Promise<ProductStatusResponse> {
  const { data } = await apiClient.post<ProductStatusResponse>(
    `/products/${id}/motivations/regenerate`
  );
  return data;
}
