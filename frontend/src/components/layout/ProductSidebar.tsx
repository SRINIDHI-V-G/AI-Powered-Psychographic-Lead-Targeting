'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Brain,
  Search,
  Trophy,
  BarChart2,
  CheckCircle2,
  Circle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useProductStatus } from '@/lib/hooks/useProducts';

interface ProductSidebarProps {
  productId: string;
}

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

export function ProductSidebar({ productId }: ProductSidebarProps) {
  const pathname = usePathname();
  const base = `/products/${productId}`;
  const { data: status } = useProductStatus(productId);

  const step = status?.pipeline_step ?? 0;
  const running = ['processing', 'discovering', 'nlp_processing', 'ocean_scoring', 'matching', 'ranking'].includes(status?.status ?? '');

  const navItems = [
    { href: base, label: 'Overview', icon: LayoutDashboard },
    { href: `${base}/motivations`, label: 'AI Motivations', icon: Brain },
    { href: `${base}/discovery`, label: 'Discovered Users', icon: Search },
    { href: `${base}/leads`, label: 'Lead Rankings', icon: Trophy },
    { href: `${base}/analytics`, label: 'Analytics', icon: BarChart2 },
  ];

  return (
    <aside className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-y-auto">
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
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

      <div className="px-3 py-4 border-t border-slate-100">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Pipeline Status
        </p>
        <ul className="space-y-1.5">
          {pipelineStages.map((stage, i) => {
            const done = step > i;
            const active = running && step === i + 1;
            return (
              <li key={stage} className="flex items-center gap-2">
                {active ? (
                  <Loader2 size={14} className="text-indigo-500 animate-spin shrink-0" />
                ) : done ? (
                  <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                ) : (
                  <Circle size={14} className="text-slate-300 shrink-0" />
                )}
                <span
                  className={cn(
                    'text-xs',
                    done ? 'text-green-600' : active ? 'text-indigo-600 font-medium' : 'text-slate-400'
                  )}
                >
                  {stage}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
