'use client';

import { formatRelative } from '@/lib/utils';
import type { ActivityEvent } from '@/lib/types/api';

interface ActivityLogProps {
  events: ActivityEvent[];
}

const eventColors: Record<string, string> = {
  discovery_complete: 'bg-indigo-500',
  nlp_complete: 'bg-cyan-500',
  ocean_complete: 'bg-teal-500',
  matching_complete: 'bg-amber-500',
  ranking_complete: 'bg-green-500',
  pipeline_failed: 'bg-red-500',
  product_created: 'bg-purple-500',
};

export function ActivityLog({ events }: ActivityLogProps) {
  if (!events.length) {
    return <p className="text-sm text-slate-400 py-4 text-center">No recent activity</p>;
  }
  return (
    <ul className="space-y-3">
      {events.slice(0, 10).map((event, i) => {
        const color = eventColors[event.event_type] ?? 'bg-slate-400';
        return (
          <li key={i} className="flex items-start gap-3">
            <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${color}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-700 truncate">
                <span className="font-medium">{event.product_name}</span>
                {' — '}
                {event.detail}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">{formatRelative(event.occurred_at)}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
