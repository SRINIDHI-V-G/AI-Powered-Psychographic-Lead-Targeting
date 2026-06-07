import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

/**
 * Server-side auth check.
 * Reads the HttpOnly cookie (invisible to client JS) and probes the backend.
 * Returns 200 + company profile if authenticated, 401 otherwise.
 * Used by AuthGuard on mount to determine whether to redirect to /login.
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
  const session = req.cookies.get('pl_session');

  if (!session?.value) {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }

  try {
    const verify = await fetch(`${BACKEND_URL}/api/v1/companies/me`, {
      headers: { 'X-API-Key': session.value },
    });

    if (!verify.ok) {
      // Cookie exists but key is invalid — clear the stale cookie.
      const response = NextResponse.json({ authenticated: false }, { status: 401 });
      response.cookies.set('pl_session', '', {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict',
        path: '/',
        maxAge: 0,
      });
      return response;
    }

    const company = await verify.json();
    return NextResponse.json({ authenticated: true, company });
  } catch {
    // Backend unreachable — treat as unauthenticated (don't clear cookie,
    // the backend may be temporarily down).
    return NextResponse.json({ authenticated: false, reason: 'backend_unavailable' }, { status: 503 });
  }
}
