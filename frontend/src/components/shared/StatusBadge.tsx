'use client';

import { cn } from '@/lib/utils';
import type { ProductStatus } from '@/lib/types/api';

interface StatusBadgeProps {
  status: ProductStatus | string;
  className?: string;
}

const statusConfig: Record<string, { label: string; style: string }> = {
  pending: { label: 'Pending', style: 'bg-slate-100 text-slate-600' },
  processing: { label: 'Processing', style: 'bg-blue-100 text-blue-700 animate-pulse' },
  motivations_generated: { label: 'Motivations Ready', style: 'bg-purple-100 text-purple-700' },
  discovering: { label: 'Discovering', style: 'bg-indigo-100 text-indigo-700 animate-pulse' },
  nlp_processing: { label: 'NLP Processing', style: 'bg-cyan-100 text-cyan-700 animate-pulse' },
  ocean_scoring: { label: 'OCEAN Scoring', style: 'bg-teal-100 text-teal-700 animate-pulse' },
  matching: { label: 'Matching', style: 'bg-amber-100 text-amber-700 animate-pulse' },
  ranking: { label: 'Ranking', style: 'bg-orange-100 text-orange-700 animate-pulse' },
  ranked: { label: 'Complete', style: 'bg-green-100 text-green-700' },
  failed: { label: 'Failed', style: 'bg-red-100 text-red-700' },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? { label: status, style: 'bg-slate-100 text-slate-600' };
  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        config.style,
        className
      )}
    >
      {config.label}
    </span>
  );
}
