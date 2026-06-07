/**
 * Auth helpers — cookie-based session model.
 *
 * The API key is stored ONLY in an HttpOnly cookie (set server-side by
 * /api/auth/login). It is never placed in localStorage or any JS-readable
 * storage, so XSS cannot steal it.
 *
 * Auth state is determined by calling /api/auth/me (a Next.js API route that
 * reads the HttpOnly cookie and validates it against the backend). This costs
 * one HTTP round-trip on mount but is the only correct approach — JS cannot
 * read HttpOnly cookies.
 *
 * Demo mode product ID is stored in sessionStorage: it is not a secret
 * (it is a public UUID), and session-scoped storage is cleaner for demo data.
 */

const DEMO_KEY = 'psycholead_demo_mode';

// ── Auth API calls ────────────────────────────────────────────────────────────

/** Validate the key against the backend, then set the HttpOnly session cookie. */
export async function loginWithKey(api_key: string): Promise<{
  ok: boolean;
  error?: string;
  company?: unknown;
}> {
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key }),
    });
    const data = await res.json();
    if (!res.ok) return { ok: false, error: data.error ?? 'Login failed.' };
    return { ok: true, company: data.company };
  } catch {
    return { ok: false, error: 'Network error. Is the server running?' };
  }
}

/** Clear the session cookie via the server-side logout route. */
export async function logoutSession(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' });
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(DEMO_KEY);
  }
}

/**
 * Check auth state by probing the backend through the server-side /api/auth/me
 * route (which reads the HttpOnly cookie).
 * Returns true when authenticated, false otherwise.
 * Also returns false when the backend is unreachable to avoid false positives.
 */
export async function checkAuthStatus(): Promise<boolean> {
  try {
    const res = await fetch('/api/auth/me', { cache: 'no-store' });
    if (res.status === 503) return false; // backend down — don't redirect to login
    return res.ok;
  } catch {
    return false;
  }
}

// ── Demo mode ─────────────────────────────────────────────────────────────────

/** Mark the current session as demo mode and store the demo product ID. */
export function setDemoMode(productId: string): void {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(DEMO_KEY, productId);
  }
}

export function getDemoProductId(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(DEMO_KEY);
}

export function isDemoMode(): boolean {
  return Boolean(getDemoProductId());
}
