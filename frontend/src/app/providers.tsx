'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from 'sonner';
import { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { checkAuthStatus, logoutSession } from '@/lib/auth';
import { clearApiKey } from '@/lib/api/client';

const PUBLIC_PATHS = ['/login'];

/**
 * AuthGuard — enforces authentication on all non-public routes.
 *
 * Uses an async server-side cookie check (via /api/auth/me) because the
 * API key is stored in an HttpOnly cookie that JS cannot read directly.
 *
 * Renders null while the check is in flight to avoid a flash of protected
 * content. Once checked, either the children render or the user is redirected.
 */
function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  // Auth check runs ONCE on mount only.
  // Re-running on every pathname change caused spurious /login redirects:
  // navigating to /products triggered a fresh checkAuthStatus() which could
  // transiently fail (network hiccup, HMR reload) and bounce the user back.
  // Mid-session 401/403 responses are already handled by the auth:unauthorized
  // event listener below (fired by the axios interceptor in lib/api/client.ts).
  useEffect(() => {
    if (PUBLIC_PATHS.includes(pathname)) {
      setChecked(true);
      return;
    }

    checkAuthStatus().then((ok) => {
      if (!ok) {
        router.replace('/login');
      } else {
        setChecked(true);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally empty — only check on initial mount

  // Listen for 401/403 responses from the backend (e.g., key rotated by admin).
  useEffect(() => {
    const handler = async () => {
      clearApiKey();
      await logoutSession();
      router.replace('/login');
    };
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, [router]);

  // Render nothing until auth state is confirmed, preventing a flash of
  // protected content before the redirect fires.
  if (!checked) return null;

  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthGuard>{children}</AuthGuard>
      <Toaster position="top-right" richColors />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
