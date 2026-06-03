import axios from 'axios';
import { getApiKey } from '../auth';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  const key = getApiKey();
  if (key) {
    config.headers['X-API-Key'] = key;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 || error.response?.status === 403) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('auth:unauthorized'));
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;

export async function downloadWithAuth(
  url: string,
  filename: string
): Promise<void> {
  const key = getApiKey();
  const response = await fetch(url, {
    headers: key ? { 'X-API-Key': key } : {},
  });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}
