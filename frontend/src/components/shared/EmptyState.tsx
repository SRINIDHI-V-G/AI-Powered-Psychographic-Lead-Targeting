'use client';

import { Inbox } from 'lucide-react';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title = 'No data yet',
  description,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-16 text-center gap-3',
        className
      )}
    >
      <div className="text-slate-300">
        {icon ?? <Inbox size={48} />}
      </div>
      <div>
        <p className="text-slate-600 font-medium">{title}</p>
        {description && <p className="text-slate-400 text-sm mt-1">{description}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
