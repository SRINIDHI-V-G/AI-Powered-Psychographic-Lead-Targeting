'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from 'sonner';
import { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { checkAuthStatus, logoutSession } from '@/lib/auth';
import { clearApiKey, storeApiKey } from '@/lib/api/client';

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

  useEffect(() => {
    // Local dev bypass: skip login entirely when NEXT_PUBLIC_SKIP_AUTH=true.
    // The middleware auto-injects DEV_API_KEY for all /api/v1/* requests.
    if (process.env.NEXT_PUBLIC_SKIP_AUTH === 'true') {
      setChecked(true);
      return;
    }

    if (PUBLIC_PATHS.includes(pathname)) {
      setChecked(true);
      return;
    }

    checkAuthStatus().then(async (ok) => {
      if (!ok) {
        router.replace('/login');
      } else {
        if (typeof window !== 'undefined' && !sessionStorage.getItem('pl_api_key')) {
          try {
            const res = await fetch('/api/auth/key');
            if (res.ok) {
              const { api_key } = await res.json() as { api_key: string };
              storeApiKey(api_key);
            }
          } catch {
            // Non-fatal
          }
        }
        setChecked(true);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Listen for 401/403 responses from the backend.
  // In bypass mode this is a no-op — the middleware always injects the dev key.
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_SKIP_AUTH === 'true') return;
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
