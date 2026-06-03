'use client';

import { cn } from '@/lib/utils';

interface OceanData {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
}

interface OceanBarsProps {
  data: OceanData;
  scale?: number; // default 100
  className?: string;
  compact?: boolean;
}

const DIMENSIONS = [
  { key: 'openness' as const, label: 'O', fullLabel: 'Openness', color: '#6366f1' },
  { key: 'conscientiousness' as const, label: 'C', fullLabel: 'Conscientiousness', color: '#0891b2' },
  { key: 'extraversion' as const, label: 'E', fullLabel: 'Extraversion', color: '#f59e0b' },
  { key: 'agreeableness' as const, label: 'A', fullLabel: 'Agreeableness', color: '#10b981' },
  { key: 'neuroticism' as const, label: 'N', fullLabel: 'Neuroticism', color: '#ef4444' },
];

export function OceanBars({ data, scale = 100, className, compact = false }: OceanBarsProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {DIMENSIONS.map(({ key, label, fullLabel, color }) => {
        const raw = data[key] ?? 0;
        const pct = Math.min(100, (raw / scale) * 100);
        const display = (raw / 10).toFixed(1);
        return (
          <div key={key} className="flex items-center gap-2">
            <span
              className={cn(
                'font-bold shrink-0',
                compact ? 'text-xs w-4' : 'text-xs w-20 text-slate-600'
              )}
              title={fullLabel}
            >
              {compact ? label : fullLabel}
            </span>
            <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            {!compact && (
              <span className="text-xs font-semibold text-slate-600 w-8 text-right">
                {display}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export { DIMENSIONS as OCEAN_DIMENSIONS };
