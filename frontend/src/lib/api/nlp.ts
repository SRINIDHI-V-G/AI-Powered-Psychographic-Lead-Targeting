import apiClient from './client';
import type { NlpStatus, NlpResult } from '../types/api';

export async function getNlpStatus(productId: string): Promise<NlpStatus> {
  const { data } = await apiClient.get<NlpStatus>(`/products/${productId}/nlp/status`);
  return data;
}

export async function triggerNlp(productId: string): Promise<void> {
  await apiClient.post(`/products/${productId}/nlp/trigger`);
}

export async function getUserNlp(productId: string, userId: string): Promise<NlpResult> {
  const { data } = await apiClient.get<NlpResult>(
    `/products/${productId}/discovery/users/${userId}/nlp`
  );
  return data;
}
