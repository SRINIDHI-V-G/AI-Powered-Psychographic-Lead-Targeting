'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { useLeadsAnalytics } from '@/lib/hooks/useAnalytics';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-xl font-bold text-slate-800">{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

export default function AnalyticsPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data, isLoading, isError, refetch } = useLeadsAnalytics(id);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" label="Loading analytics..." />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to load analytics"
        message="Rankings may not be available yet."
        onRetry={() => void refetch()}
      />
    );
  }

  if (!data) {
    return <EmptyState title="No analytics available" />;
  }

  const qs = data.quality_summary;
  const fd = data.final_score_distribution;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Lead Analytics</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Score distributions and quality summary
        </p>
      </div>

      {/* Quality summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Ranked" value={data.total_ranked} />
        <StatCard label="Passing Quality" value={`${qs.pct_passing.toFixed(0)}%`} />
        <StatCard label="Min Confidence (rec.)" value={qs.recommended_min_confidence.toFixed(2)} />
        <StatCard label="Flagged Low Confidence" value={qs.flagged_low_confidence} />
      </div>

      {/* Score distribution */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-700 mb-1">Final Score Distribution</h2>
        <p className="text-xs text-slate-400 mb-4">
          Mean: {(fd.mean / 10).toFixed(1)} · Median: {(fd.median / 10).toFixed(1)} · Std Dev:{' '}
          {(fd.std_dev / 10).toFixed(1)}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={fd.histogram} margin={{ top: 0, right: 0, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="range" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
            />
            <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Confidence distribution */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-700 mb-4">Confidence Distribution</h2>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart
            data={data.confidence_distribution.histogram}
            margin={{ top: 0, right: 0, bottom: 0, left: -10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="range" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
            />
            <Bar dataKey="count" fill="#0891b2" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top motivation categories */}
      {data.top_motivation_categories.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-700 mb-4">Top Motivation Categories</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              layout="vertical"
              data={data.top_motivation_categories.slice(0, 8)}
              margin={{ top: 0, right: 30, bottom: 0, left: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="category"
                tick={{ fontSize: 11 }}
                width={150}
              />
              <Tooltip
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
              />
              <Bar dataKey="count" fill="#f59e0b" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Quality flags summary */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-700 mb-3">Quality Flags</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-lg font-bold text-slate-800">{qs.passing_all_filters}</p>
            <p className="text-xs text-slate-500">Passing All Filters</p>
          </div>
          <div className="bg-amber-50 rounded-lg p-3">
            <p className="text-lg font-bold text-amber-700">{qs.flagged_heuristic_ocean}</p>
            <p className="text-xs text-slate-500">Heuristic OCEAN</p>
          </div>
          <div className="bg-red-50 rounded-lg p-3">
            <p className="text-lg font-bold text-red-700">{qs.flagged_insufficient_content}</p>
            <p className="text-xs text-slate-500">Insufficient Content</p>
          </div>
        </div>
      </div>

      {/* Calibration notes */}
      {data.calibration_notes.length > 0 && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4">
          <h2 className="font-semibold text-indigo-700 mb-2">Calibration Notes</h2>
          <ul className="space-y-1">
            {data.calibration_notes.map((note, i) => (
              <li key={i} className="text-sm text-indigo-700 flex items-start gap-1.5">
                <span className="mt-0.5">•</span>
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
