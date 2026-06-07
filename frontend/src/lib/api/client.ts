import axios from 'axios';

/**
 * Axios client for all /api/v1/* requests.
 *
 * Authentication: the X-API-Key header is injected by Next.js middleware
 * (src/middleware.ts) which reads the HttpOnly pl_session cookie server-side.
 * This client intentionally does NOT read or forward any API key from
 * client-accessible storage — doing so would reintroduce the XSS risk.
 *
 * withCredentials: true ensures the browser sends the pl_session cookie
 * with every same-origin request so the middleware can read it.
 */
const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  withCredentials: true,
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
