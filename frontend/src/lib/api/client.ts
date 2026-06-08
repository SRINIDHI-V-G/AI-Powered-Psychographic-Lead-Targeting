import axios from 'axios';

const SESSION_KEY = 'pl_api_key';

/** Store the API key for use by the axios client (call after successful login). */
export function storeApiKey(key: string): void {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(SESSION_KEY, key);
  }
}

/** Clear the stored API key (call on logout). */
export function clearApiKey(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(SESSION_KEY);
  }
}

/**
 * Axios client for all /api/v1/* requests.
 *
 * Authentication: the X-API-Key header is read from sessionStorage and injected
 * via a request interceptor. The key is stored there by storeApiKey() after login.
 *
 * Note: the Next.js middleware approach (injecting from HttpOnly cookie) was
 * abandoned because Next.js 14 does not forward middleware-modified request
 * headers through next.config.js rewrites to external servers — the rewrite
 * creates a fresh HTTP request using only the original browser headers.
 */
const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  withCredentials: true,
});

// Inject X-API-Key on every outgoing request
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const key = sessionStorage.getItem(SESSION_KEY);
    if (key) {
      config.headers['X-API-Key'] = key;
    }
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
  },
);

export default apiClient;

export async function downloadWithAuth(url: string, filename: string): Promise<void> {
  const response = await fetch(url, {
    credentials: 'include',  // send pl_session cookie so middleware injects X-API-Key
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
