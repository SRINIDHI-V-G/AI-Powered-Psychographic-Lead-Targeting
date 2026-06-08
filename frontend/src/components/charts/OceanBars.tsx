'use client';

import { cn } from '@/lib/utils';

interface OceanData {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  /** Either neuroticism or stability — use the 'stability' key to show "S" label */
  neuroticism?: number;
  stability?: number;
}

interface OceanBarsProps {
  data: OceanData;
  scale?: number; // default 100
  className?: string;
  compact?: boolean;
}

const DIMENSIONS_NEUROTICISM = [
  { key: 'openness' as const,         label: 'O', fullLabel: 'Openness',          color: '#6366f1' },
  { key: 'conscientiousness' as const, label: 'C', fullLabel: 'Conscientiousness', color: '#6366f1' },
  { key: 'extraversion' as const,      label: 'E', fullLabel: 'Extraversion',      color: '#6366f1' },
  { key: 'agreeableness' as const,     label: 'A', fullLabel: 'Agreeableness',     color: '#6366f1' },
  { key: 'neuroticism' as const,       label: 'N', fullLabel: 'Neuroticism',       color: '#6366f1' },
];

const DIMENSIONS_STABILITY = [
  { key: 'openness' as const,         label: 'O', fullLabel: 'Openness',           color: '#6366f1' },
  { key: 'conscientiousness' as const, label: 'C', fullLabel: 'Conscientiousness', color: '#6366f1' },
  { key: 'extraversion' as const,      label: 'E', fullLabel: 'Extraversion',      color: '#6366f1' },
  { key: 'agreeableness' as const,     label: 'A', fullLabel: 'Agreeableness',     color: '#6366f1' },
  { key: 'stability' as const,         label: 'S', fullLabel: 'Stability',         color: '#6366f1' },
];

export function OceanBars({ data, scale = 100, className, compact = false }: OceanBarsProps) {
  const useStability = 'stability' in data && data.stability !== undefined;
  const dims = useStability ? DIMENSIONS_STABILITY : DIMENSIONS_NEUROTICISM;

  return (
    <div className={cn('space-y-1.5', className)}>
      {dims.map(({ key, label, fullLabel, color }) => {
        const raw = (data as unknown as Record<string, number | undefined>)[key] ?? 0;
        const pct = Math.min(100, (raw / scale) * 100);
        // If scale is 10 (motivation profiles), raw is already 0-10; show directly.
        // If scale is 100 (user OCEAN scores), divide by 10 to show 0-10.
        const display = scale === 10 ? raw.toFixed(1) : (raw / 10).toFixed(1);
        return (
          <div key={key} className="flex items-center gap-2">
            <span
              className={cn(
                'font-bold shrink-0 text-slate-500',
                compact ? 'text-xs w-4' : 'text-xs w-4'
              )}
              title={fullLabel}
            >
              {label}
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

export { DIMENSIONS_NEUROTICISM as OCEAN_DIMENSIONS };
