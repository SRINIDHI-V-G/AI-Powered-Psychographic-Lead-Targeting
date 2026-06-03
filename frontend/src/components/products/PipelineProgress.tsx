'use client';

import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import { cn, getPipelineLabel, isRunning } from '@/lib/utils';
import type { ProductStatus } from '@/lib/types/api';

interface PipelineProgressProps {
  step: number;
  status: ProductStatus;
}

const steps = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

export function PipelineProgress({ step, status }: PipelineProgressProps) {
  const running = isRunning(status);
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {steps.map((s) => {
        const done = step > s;
        const current = step === s && running;
        const label = getPipelineLabel(s);
        return (
          <div key={s} className="flex flex-col items-center gap-1 min-w-[70px]">
            <div className="flex items-center gap-0.5 w-full">
              {s > 0 && (
                <div className={cn('h-px flex-1', done ? 'bg-indigo-400' : 'bg-slate-200')} />
              )}
              {current ? (
                <Loader2 size={18} className="text-indigo-500 animate-spin" />
              ) : done ? (
                <CheckCircle2 size={18} className="text-green-500" />
              ) : (
                <Circle
                  size={18}
                  className={cn(step === s ? 'text-indigo-400' : 'text-slate-300')}
                />
              )}
              {s < 9 && (
                <div className={cn('h-px flex-1', done ? 'bg-indigo-400' : 'bg-slate-200')} />
              )}
            </div>
            <span
              className={cn(
                'text-xs text-center leading-tight',
                done ? 'text-green-600' : current ? 'text-indigo-600 font-medium' : 'text-slate-400'
              )}
            >
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
