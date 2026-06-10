import apiClient from './client';
import type {
  DiscoveryJob,
  DiscoveredUsersResponse,
  PlatformBreakdown,
  UserContent,
  ProviderStatus,
} from '../types/api';

export async function getProviderStatus(): Promise<ProviderStatus> {
  const { data } = await apiClient.get<ProviderStatus>('/discovery/provider/status');
  return data;
}

export async function startDiscovery(
  productId: string,
  maxUsers = 150
): Promise<DiscoveryJob> {
  const { data } = await apiClient.post<DiscoveryJob>(
    `/products/${productId}/discovery/start`,
    { max_users: maxUsers, search_config: {} }
  );
  return data;
}

export async function getDiscoveryJobs(productId: string): Promise<DiscoveryJob[]> {
  const { data } = await apiClient.get<DiscoveryJob[]>(
    `/products/${productId}/discovery/jobs`
  );
  return data;
}

export async function getDiscoveryJob(
  productId: string,
  jobId: string
): Promise<DiscoveryJob> {
  const { data } = await apiClient.get<DiscoveryJob>(
    `/products/${productId}/discovery/jobs/${jobId}`
  );
  return data;
}

export async function getDiscoveredUsers(
  productId: string,
  params: { page?: number; limit?: number; job_id?: string } = {}
): Promise<DiscoveredUsersResponse> {
  const { data } = await apiClient.get<DiscoveredUsersResponse>(
    `/products/${productId}/discovery/users`,
    { params }
  );
  return data;
}

export async function getUserContent(
  productId: string,
  userId: string
): Promise<UserContent[]> {
  const { data } = await apiClient.get<UserContent[]>(
    `/products/${productId}/discovery/users/${userId}/content`
  );
  return data;
}

export async function getPlatformStats(productId: string): Promise<PlatformBreakdown[]> {
  const { data } = await apiClient.get<PlatformBreakdown[]>(
    `/products/${productId}/discovery/platform-stats`
  );
  return data;
}
