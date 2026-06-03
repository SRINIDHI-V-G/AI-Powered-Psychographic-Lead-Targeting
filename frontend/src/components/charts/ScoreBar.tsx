'use client';

import { cn } from '@/lib/utils';

interface ScoreBarProps {
  label: string;
  value: number;
  max?: number;
  color?: string;
  className?: string;
  showValue?: boolean;
}

export function ScoreBar({
  label,
  value,
  max = 100,
  color = '#6366f1',
  className,
  showValue = true,
}: ScoreBarProps) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex justify-between text-xs text-slate-600">
        <span>{label}</span>
        {showValue && <span className="font-semibold">{(value / 10).toFixed(1)}</span>}
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}
