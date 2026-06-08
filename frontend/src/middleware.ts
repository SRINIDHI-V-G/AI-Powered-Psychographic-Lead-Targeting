import { NextRequest, NextResponse } from 'next/server';

/**
 * Injects X-API-Key into every /api/v1/* request before Next.js rewrites it
 * to the FastAPI backend.
 *
 * Source priority:
 *   1. pl_session HttpOnly cookie (set after login)
 *   2. DEV_API_KEY environment variable (local dev bypass — no login needed)
 */
export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/api/v1/')) {
    const session = request.cookies.get('pl_session');
    const apiKey = session?.value ?? process.env.DEV_API_KEY;

    if (apiKey) {
      const modifiedHeaders = new Headers(request.headers);
      modifiedHeaders.set('X-API-Key', apiKey);
      return NextResponse.next({ request: { headers: modifiedHeaders } });
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/api/v1/:path*'],
};
