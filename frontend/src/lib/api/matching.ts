import apiClient from './client';
import type { MatchStatus, LeadsResponse, LeadDetail } from '../types/api';

export async function triggerMatch(productId: string): Promise<void> {
  await apiClient.post(`/products/${productId}/match/trigger`);
}

export async function getMatchStatus(productId: string): Promise<MatchStatus> {
  const { data } = await apiClient.get<MatchStatus>(`/products/${productId}/match/status`);
  return data;
}

export async function getLeads(
  productId: string,
  params: {
    page?: number;
    page_size?: number;
    min_score?: number;
    min_confidence?: number;
    sort?: 'top' | 'bottom';
  } = {}
): Promise<LeadsResponse> {
  const { data } = await apiClient.get<LeadsResponse>(`/products/${productId}/leads`, {
    params,
  });
  return data;
}

export async function getLeadDetail(
  productId: string,
  userId: string
): Promise<LeadDetail> {
  const { data } = await apiClient.get<LeadDetail>(
    `/products/${productId}/leads/${userId}`
  );
  return data;
}
