import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

// Cookie lifetime: 30 days. The backend key itself never expires (BUG-001 fix
// adds a rotation endpoint), so the cookie can be long-lived.
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

export async function POST(req: NextRequest): Promise<NextResponse> {
  let api_key: string | undefined;

  try {
    const body = await req.json();
    api_key = typeof body?.api_key === 'string' ? body.api_key.trim() : undefined;
  } catch {
    return NextResponse.json({ error: 'Invalid request body.' }, { status: 400 });
  }

  if (!api_key) {
    return NextResponse.json({ error: 'api_key is required.' }, { status: 400 });
  }

  // Validate the key against the backend before storing it in a cookie.
  let company: unknown;
  try {
    const verify = await fetch(`${BACKEND_URL}/api/v1/companies/me`, {
      headers: { 'X-API-Key': api_key },
    });

    if (!verify.ok) {
      const status = verify.status === 403 ? 403 : 401;
      return NextResponse.json(
        { error: verify.status === 403 ? 'Account is inactive.' : 'Invalid API key.' },
        { status },
      );
    }

    company = await verify.json();
  } catch {
    return NextResponse.json(
      { error: 'Backend unreachable. Is the server running?' },
      { status: 502 },
    );
  }

  const response = NextResponse.json({ ok: true, company });

  // HttpOnly: not readable by JavaScript — the primary XSS defence.
  // Secure: sent only over HTTPS in production.
  // SameSite=Strict: not sent with cross-site requests — CSRF defence.
  response.cookies.set('pl_session', api_key, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: COOKIE_MAX_AGE,
  });

  return response;
}
