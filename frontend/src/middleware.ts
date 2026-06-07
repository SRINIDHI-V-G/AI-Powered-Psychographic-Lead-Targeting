import { NextRequest, NextResponse } from 'next/server';

/**
 * Security middleware: read the HttpOnly session cookie and inject the
 * X-API-Key header into every /api/v1/* request before Next.js rewrites it
 * to the FastAPI backend.
 *
 * The cookie is set server-side by /api/auth/login (HttpOnly, Secure, SameSite=Strict)
 * so it is never accessible to JavaScript — this prevents XSS-based key theft.
 *
 * The middleware must run BEFORE Next.js rewrites so the injected header is
 * forwarded to the backend. This is the default execution order in Next.js 13+.
 */
export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/api/v1/')) {
    const session = request.cookies.get('pl_session');

    if (session?.value) {
      const modifiedHeaders = new Headers(request.headers);
      modifiedHeaders.set('X-API-Key', session.value);

      return NextResponse.next({
        request: { headers: modifiedHeaders },
      });
    }
  }

  return NextResponse.next();
}

export const config = {
  // Run on all /api/v1/* requests; skip Next.js internals and static assets.
  matcher: ['/api/v1/:path*'],
};
