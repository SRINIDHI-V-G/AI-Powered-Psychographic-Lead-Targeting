import apiClient from './client';
import type { LeadsSummary, LeadAnalytics, LeadInspect } from '../types/api';

export async function getLeadsSummary(productId: string): Promise<LeadsSummary> {
  const { data } = await apiClient.get<LeadsSummary>(
    `/products/${productId}/leads/summary`
  );
  return data;
}

export async function getLeadsAnalytics(productId: string): Promise<LeadAnalytics> {
  const { data } = await apiClient.get<LeadAnalytics>(
    `/products/${productId}/leads/analytics`
  );
  return data;
}

export async function inspectLead(
  productId: string,
  userId: string
): Promise<LeadInspect> {
  const { data } = await apiClient.get<LeadInspect>(
    `/products/${productId}/leads/${userId}/inspect`
  );
  return data;
}

export async function exportLeads(
  productId: string,
  format: 'csv' | 'json',
  minScore = 0,
  minConfidence = 0
): Promise<{ url: string }> {
  const params = new URLSearchParams({
    format,
    min_score: String(minScore),
    min_confidence: String(minConfidence),
  });
  return { url: `/api/v1/products/${productId}/leads/export?${params}` };
}
