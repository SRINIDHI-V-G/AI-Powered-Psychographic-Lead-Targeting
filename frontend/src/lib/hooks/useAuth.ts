'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getApiKey, setApiKey, removeApiKey, isAuthenticated, setDemoMode } from '../auth';
import { setupDemo } from '../api/demo';
import apiClient from '../api/client';

export function useAuth() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAuthenticated(isAuthenticated());
  }, []);

  const login = useCallback(
    async (key: string) => {
      if (!key.trim()) {
        setError('API key cannot be empty');
        return false;
      }
      setLoading(true);
      setError(null);
      try {
        // Verify key works by calling /companies/me
        const { data } = await apiClient.get('/companies/me', {
          headers: { 'X-API-Key': key },
        });
        if (data) {
          setApiKey(key);
          setAuthenticated(true);
          router.push('/');
          return true;
        }
        setError('Invalid API key');
        return false;
      } catch {
        setError('Invalid API key or server unreachable');
        return false;
      } finally {
        setLoading(false);
      }
    },
    [router]
  );

  const loginDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await setupDemo();
      setApiKey(result.api_key);
      setDemoMode(result.product_id);
      setAuthenticated(true);
      router.push('/');
      return true;
    } catch {
      setError('Failed to set up demo. Is the backend running?');
      return false;
    } finally {
      setLoading(false);
    }
  }, [router]);

  const logout = useCallback(() => {
    removeApiKey();
    setAuthenticated(false);
    router.push('/login');
  }, [router]);

  return { authenticated, loading, error, login, loginDemo, logout, getApiKey };
}
