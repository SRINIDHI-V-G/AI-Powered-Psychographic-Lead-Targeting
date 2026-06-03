'use client';

import { cn, getTier } from '@/lib/utils';
import type { LeadTier } from '@/lib/types/api';

interface TierBadgeProps {
  score?: number;
  tier?: LeadTier;
  className?: string;
}

const tierStyles: Record<LeadTier, string> = {
  Hot: 'bg-red-100 text-red-700 border border-red-200',
  Warm: 'bg-orange-100 text-orange-700 border border-orange-200',
  Cold: 'bg-blue-100 text-blue-700 border border-blue-200',
};

export function TierBadge({ score, tier, className }: TierBadgeProps) {
  const resolvedTier: LeadTier = tier ?? (score !== undefined ? getTier(score) : 'Cold');
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold',
        tierStyles[resolvedTier],
        className
      )}
    >
      {resolvedTier === 'Hot' && '🔥 '}
      {resolvedTier}
    </span>
  );
}
