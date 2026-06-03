import apiClient from './client';
import type { DashboardOverview } from '../types/api';

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const { data } = await apiClient.get<DashboardOverview>('/dashboard/overview');
  return data;
}
