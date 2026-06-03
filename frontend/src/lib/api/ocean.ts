import apiClient from './client';
import type { OceanStatus, OceanScore } from '../types/api';

export async function getOceanStatus(productId: string): Promise<OceanStatus> {
  const { data } = await apiClient.get<OceanStatus>(`/products/${productId}/ocean/status`);
  return data;
}

export async function triggerOcean(productId: string): Promise<void> {
  await apiClient.post(`/products/${productId}/ocean/trigger`);
}

export async function getUserOcean(productId: string, userId: string): Promise<OceanScore> {
  const { data } = await apiClient.get<OceanScore>(
    `/products/${productId}/discovery/users/${userId}/ocean`
  );
  return data;
}
