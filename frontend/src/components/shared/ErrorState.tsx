'use client';

import { AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-16 text-center gap-3',
        className
      )}
    >
      <AlertCircle className="text-red-400" size={48} />
      <div>
        <p className="text-slate-700 font-medium">{title}</p>
        {message && <p className="text-slate-400 text-sm mt-1 max-w-md">{message}</p>}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition"
        >
          Try Again
        </button>
      )}
    </div>
  );
}
