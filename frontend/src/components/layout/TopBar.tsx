'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Lightbulb, RotateCcw, Play, LogOut, LayoutGrid } from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';
import { isDemoMode, loginWithKey, setDemoMode } from '@/lib/auth';
import { storeApiKey } from '@/lib/api/client';
import { setupDemo } from '@/lib/api/demo';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

export function TopBar() {
  const { logout } = useAuth();
  const [demo, setDemo] = useState(false);
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    setDemo(isDemoMode());
  }, []);

  const handleResetDemo = async () => {
    try {
      const result = await setupDemo();
      const loginResult = await loginWithKey(result.api_key);
      if (!loginResult.ok) throw new Error(loginResult.error);
      storeApiKey(result.api_key);
      setDemoMode(result.product_id);
      qc.clear();
      toast.success('Demo reset');
      router.push('/');
    } catch {
      toast.error('Failed to reset demo');
    }
  };

  const handleRunDemo = async () => {
    try {
      const result = await setupDemo();
      const loginResult = await loginWithKey(result.api_key);
      if (!loginResult.ok) throw new Error(loginResult.error);
      storeApiKey(result.api_key);
      setDemoMode(result.product_id);
      qc.clear();
      toast.success('Demo started');
      router.push(`/products/${result.product_id}`);
    } catch {
      toast.error('Failed to run demo');
    }
  };

  return (
    <header className="h-14 bg-indigo-950 flex items-center px-4 gap-4 shrink-0 z-30">
      <div className="flex items-center gap-2 mr-auto">
        <div className="w-7 h-7 bg-indigo-500 rounded-lg flex items-center justify-center">
          <Lightbulb size={16} className="text-white" />
        </div>
        <span className="text-white font-bold text-base tracking-tight">PsychoLead AI</span>
        {demo && (
          <span className="ml-2 px-2 py-0.5 bg-amber-500 text-white text-xs font-bold rounded">
            DEMO MODE
          </span>
        )}
      </div>

      <nav className="flex items-center gap-1">
        <Link
          href="/products"
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition',
            pathname.startsWith('/products')
              ? 'bg-indigo-700 text-white'
              : 'text-slate-300 hover:bg-indigo-800 hover:text-white'
          )}
        >
          <LayoutGrid size={13} />
          Products
        </Link>
      </nav>

      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-green-400" />
        <span className="text-slate-300 text-xs">Pipeline active</span>
      </div>

      {demo && (
        <>
          <button
            onClick={handleResetDemo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 text-slate-200 text-xs hover:bg-slate-600 transition"
          >
            <RotateCcw size={12} />
            Reset Demo
          </button>
          <button
            onClick={handleRunDemo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-500 transition"
          >
            <Play size={12} />
            Re-run Demo
          </button>
        </>
      )}

      <button
        onClick={logout}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 text-slate-200 text-xs hover:bg-slate-600 transition"
      >
        <LogOut size={12} />
        Logout
      </button>
    </header>
  );
}
