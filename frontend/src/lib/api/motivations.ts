import apiClient from './client';
import type { MotivationsResponse } from '../types/api';

export async function getMotivations(productId: string): Promise<MotivationsResponse> {
  const { data } = await apiClient.get<MotivationsResponse>(`/products/${productId}/motivations`);
  return data;
}
