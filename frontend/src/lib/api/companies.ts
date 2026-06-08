import apiClient from './client';
import type { Company } from '../types/api';

export async function getMyCompany(): Promise<Company> {
  const { data } = await apiClient.get<Company>('/companies/me');
  return data;
}
