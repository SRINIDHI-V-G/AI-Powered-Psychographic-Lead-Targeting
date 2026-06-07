import { NextResponse } from 'next/server';

export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });

  // Clear both the session cookie and the demo-mode cookie.
  response.cookies.set('pl_session', '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: 0,   // Immediate expiry
  });

  return response;
}
