import { NextRequest, NextResponse } from 'next/server';

/**
 * Returns the raw API key from the HttpOnly session cookie so the client can
 * restore it to sessionStorage after a page reload (where sessionStorage is
 * cleared but the long-lived cookie survives).
 *
 * Security note: this exposes the key to JS, same as sessionStorage. The only
 * XSS defence HttpOnly provides is preventing passive reads; an attacker who
 * can run fetch() can call this endpoint regardless. The real defence is CSP.
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
  const session = req.cookies.get('pl_session');
  if (!session?.value) {
    return NextResponse.json({ error: 'No session' }, { status: 401 });
  }
  return NextResponse.json({ api_key: session.value });
}
