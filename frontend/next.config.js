/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

const nextConfig = {
  // Prevent Next.js from issuing 308 redirects for trailing slashes on /api/v1/* routes.
  // Without this, GET /api/v1/products/ → 308 → GET /api/v1/products, and the
  // redirect strips the pl_session cookie context before the middleware can inject X-API-Key.
  skipTrailingSlashRedirect: true,

  async rewrites() {
    return [
      {
        // All /api/v1/* requests are proxied to FastAPI.
        // Next.js middleware (src/middleware.ts) runs BEFORE this rewrite and
        // injects the X-API-Key header from the HttpOnly pl_session cookie.
        source: '/api/v1/:path*',
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
  eslint: {
    dirs: ['src'],
  },
};

module.exports = nextConfig;
