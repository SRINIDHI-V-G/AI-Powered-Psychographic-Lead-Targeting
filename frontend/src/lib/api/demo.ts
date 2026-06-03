import axios from 'axios';
import type { DemoSetupResponse } from '../types/api';

export async function setupDemo(): Promise<DemoSetupResponse> {
  const { data } = await axios.post<DemoSetupResponse>('/api/v1/demo/setup');
  return data;
}

export async function getDemoUsers(productId: string) {
  const { data } = await axios.get(`/api/v1/demo/${productId}/users`);
  return data;
}

export async function getDemoLeads(productId: string) {
  const { data } = await axios.get(`/api/v1/demo/${productId}/leads`);
  return data;
}
