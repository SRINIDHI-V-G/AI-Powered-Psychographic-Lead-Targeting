'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Package,
  CheckCircle2,
  Circle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDashboard } from '@/lib/hooks/useDashboard';

const navItems = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/products', label: 'Products', icon: Package },
];

const pipelineStages = [
  'Product Submitted',
  'AI Motivation Analysis',
  'User Discovery',
  'Content Collection',
  'NLP Processing',
  'OCEAN Personality Scoring',
  'Matching Engine',
  'Lead Ranking',
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: dashboard } = useDashboard();

  // On product detail pages the ProductSidebar already shows pipeline status — hide it here
  const onProductDetailPage = /^\/products\/[^/]+/.test(pathname);

  // Use max pipeline step across active products (capped at stage count)
  const maxStep = Math.min(
    dashboard?.products.reduce((acc, p) => Math.max(acc, p.pipeline_step), 0) ?? 0,
    pipelineStages.length,
  );

  return (
    <aside className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-y-auto">
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition',
                active
                  ? 'bg-indigo-50 text-indigo-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {!onProductDetailPage && (
        <div className="px-3 py-4 border-t border-slate-100">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Pipeline Status
          </p>
          <ul className="space-y-1.5">
            {pipelineStages.map((stage, i) => {
              const done = maxStep > i;
              const active = maxStep === i + 1;
              return (
                <li key={stage} className="flex items-center gap-2">
                  {done ? (
                    <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                  ) : (
                    <Circle
                      size={14}
                      className={cn('shrink-0', active ? 'text-indigo-500' : 'text-slate-300')}
                    />
                  )}
                  <span
                    className={cn(
                      'text-xs',
                      done
                        ? 'text-green-600'
                        : active
                        ? 'text-indigo-600 font-medium'
                        : 'text-slate-400'
                    )}
                  >
                    {stage}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </aside>
  );
}
