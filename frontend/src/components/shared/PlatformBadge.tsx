'use client';

import { cn } from '@/lib/utils';

interface PlatformBadgeProps {
  platform: string;
  className?: string;
}

const platformConfig: Record<string, { label: string; style: string }> = {
  instagram: { label: 'Instagram', style: 'bg-pink-100 text-pink-700' },
  reddit: { label: 'Reddit', style: 'bg-orange-100 text-orange-700' },
  twitter: { label: 'Twitter', style: 'bg-sky-100 text-sky-700' },
  x: { label: 'X', style: 'bg-sky-100 text-sky-700' },
  mock: { label: 'Mock', style: 'bg-slate-100 text-slate-600' },
};

export function PlatformBadge({ platform, className }: PlatformBadgeProps) {
  const key = platform.toLowerCase();
  const config = platformConfig[key] ?? { label: platform, style: 'bg-slate-100 text-slate-600' };
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
        config.style,
        className
      )}
    >
      {config.label}
    </span>
  );
}
