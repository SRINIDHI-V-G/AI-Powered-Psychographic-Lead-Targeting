'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  loginWithKey,
  logoutSession,
  checkAuthStatus,
  setDemoMode,
} from '../auth';
import { setupDemo } from '../api/demo';

export function useAuth() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // On mount, validate auth state via the server-side cookie check.
  // This is async because JS cannot read HttpOnly cookies directly.
  useEffect(() => {
    checkAuthStatus().then(setAuthenticated);
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
        const result = await loginWithKey(key.trim());
        if (result.ok) {
          setAuthenticated(true);
          router.push('/');
          return true;
        }
        setError(result.error ?? 'Invalid API key');
        return false;
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  const loginDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Ask the backend to seed demo data and return a fresh API key.
      const result = await setupDemo();

      // 2. Exchange that key for an HttpOnly session cookie via the auth route.
      const loginResult = await loginWithKey(result.api_key);
      if (!loginResult.ok) {
        setError(loginResult.error ?? 'Failed to establish demo session.');
        return false;
      }

      // 3. Store the demo product ID in sessionStorage (not a secret).
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

  const logout = useCallback(async () => {
    await logoutSession();
    setAuthenticated(false);
    router.push('/login');
  }, [router]);

  return { authenticated, loading, error, login, loginDemo, logout };
}
