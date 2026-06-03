'use client';

import { Users, Brain, Flame, TrendingUp } from 'lucide-react';
import { cn, formatNumber } from '@/lib/utils';
import type { DashboardOverview } from '@/lib/types/api';

interface StatsGridProps {
  data: DashboardOverview;
}

export function StatsGrid({ data }: StatsGridProps) {
  const stats = [
    {
      label: 'Users Discovered',
      value: formatNumber(data.total_discovered_users),
      icon: Users,
      color: 'bg-indigo-50 text-indigo-600',
    },
    {
      label: 'Hot Leads',
      value: formatNumber(data.hot_leads_count),
      icon: Flame,
      color: 'bg-red-50 text-red-600',
    },
    {
      label: 'Warm Leads',
      value: formatNumber(data.warm_leads_count),
      icon: TrendingUp,
      color: 'bg-orange-50 text-orange-600',
    },
    {
      label: 'Active Products',
      value: String(data.total_products),
      icon: Brain,
      color: 'bg-purple-50 text-purple-600',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map(({ label, value, icon: Icon, color }) => (
        <div key={label} className="bg-white rounded-xl border border-slate-200 p-4">
          <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center mb-3', color)}>
            <Icon size={18} />
          </div>
          <p className="text-2xl font-bold text-slate-800">{value}</p>
          <p className="text-xs text-slate-500 mt-0.5">{label}</p>
        </div>
      ))}
    </div>
  );
}
