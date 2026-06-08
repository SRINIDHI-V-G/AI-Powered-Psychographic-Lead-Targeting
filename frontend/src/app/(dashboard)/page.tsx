'use client';

import { useDashboard } from '@/lib/hooks/useDashboard';
import { StatsGrid } from '@/components/dashboard/StatsGrid';
import { ActivityLog } from '@/components/dashboard/ActivityLog';
import { MotivationCategoryBars } from '@/components/dashboard/MotivationCategoryBars';
import { DonutChart } from '@/components/charts/DonutChart';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { ErrorState } from '@/components/shared/ErrorState';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { getPipelineLabel, formatNumber } from '@/lib/utils';
import Link from 'next/link';

export default function DashboardPage() {
  const { data, isLoading, isError, refetch } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" label="Loading dashboard..." />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <ErrorState
        title="Failed to load dashboard"
        message="Make sure the backend is running at http://localhost:8000"
        onRetry={() => void refetch()}
      />
    );
  }

  // Build donut data from product platforms (approximate from discovered_users)
  const tierData = [
    { name: 'Hot', value: data.hot_leads_count, color: '#dc2626' },
    { name: 'Warm', value: data.warm_leads_count, color: '#ea580c' },
    {
      name: 'Cold',
      value: Math.max(
        0,
        data.products.reduce((a, p) => a + p.ranked_leads, 0) -
          data.hot_leads_count -
          data.warm_leads_count
      ),
      color: '#3b82f6',
    },
  ].filter((d) => d.value > 0);

  // Provider colours — keyed by provider_name from DiscoveryJob
  const PROVIDER_COLORS: Record<string, string> = {
    reddit:    '#ff4500',
    instagram: '#e1306c',
    youtube:   '#ff0000',
    mock:      '#94a3b8',
  };
  const sourceData = (data.discovery_sources ?? []).map((s) => ({
    name: s.provider.charAt(0).toUpperCase() + s.provider.slice(1),
    value: s.users_discovered,
    color: PROVIDER_COLORS[s.provider.toLowerCase()] ?? '#64748b',
  }));

  // Aggregate motivation categories from recent activity
  const motivationCats = data.products.map((p) => ({
    category: p.name,
    count: p.hot_leads,
  })).filter((c) => c.count > 0);

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Campaign Overview</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Real-time psychographic targeting pipeline
        </p>
      </div>

      <StatsGrid data={data} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Lead Tier Distribution</h2>
          <DonutChart data={tierData} />
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Discovery Sources</h2>
          <DonutChart data={sourceData} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Products Pipeline</h2>
          {data.products.length === 0 ? (
            <p className="text-sm text-slate-400 py-6 text-center">No products yet</p>
          ) : (
            <div className="space-y-3">
              {data.products.map((p) => (
                <Link
                  key={p.product_id}
                  href={`/products/${p.product_id}`}
                  className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-indigo-200 hover:bg-indigo-50 transition"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div>
                      <p className="font-medium text-slate-800 text-sm">{p.name}</p>
                      <p className="text-xs text-slate-500">
                        {getPipelineLabel(p.pipeline_step)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right text-xs text-slate-500">
                      <p>{formatNumber(p.discovered_users)} users</p>
                      <p>{formatNumber(p.hot_leads)} hot leads</p>
                    </div>
                    <StatusBadge status={p.status} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Pipeline Activity</h2>
          <ActivityLog events={data.recent_activity} />
        </div>
      </div>

      {motivationCats.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Top Motivation Categories</h2>
          <MotivationCategoryBars categories={motivationCats} />
        </div>
      )}
    </div>
  );
}
