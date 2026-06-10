'use client';

import { useProduct, useProductStatus, useRestartProduct } from '@/lib/hooks/useProducts';
import { useMatchStatus } from '@/lib/hooks/useLeads';
import { useLeadsAnalytics } from '@/lib/hooks/useAnalytics';
import { useDiscoveryJobs, usePlatformStats, useStartDiscovery } from '@/lib/hooks/useDiscovery';
import { useOceanStatus } from '@/lib/hooks/useOceanStatus';
import { useMotivations } from '@/lib/hooks/useMotivations';
import { useLeads } from '@/lib/hooks/useLeads';
import { DonutChart } from '@/components/charts/DonutChart';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { ErrorState } from '@/components/shared/ErrorState';
import { getProviderColor } from '@/lib/providerColors';
import { RotateCcw, Search } from 'lucide-react';
import { toast } from 'sonner';

export default function ProductOverviewPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data: product, isLoading, isError } = useProduct(id);
  const { data: status } = useProductStatus(id);
  const { data: matchStatus } = useMatchStatus(id);
  const { data: jobs } = useDiscoveryJobs(id);
  const { data: platformStats } = usePlatformStats(id);
  const { data: oceanStatus } = useOceanStatus(id);
  const { data: motivations } = useMotivations(id);
  const { data: analytics } = useLeadsAnalytics(id);
  const { data: leadsData } = useLeads(id, { page_size: 1, sort: 'top' });
  const { mutateAsync: restart, isPending: restarting } = useRestartProduct(id);
  const { mutateAsync: startDisc, isPending: startingDisc } = useStartDiscovery(id);

  const handleRestart = async () => {
    try {
      await restart();
      toast.success('Pipeline restarted — check back in a few minutes');
    } catch {
      toast.error('Failed to restart pipeline');
    }
  };

  const handleStartDiscovery = async () => {
    try {
      await startDisc(50);
      toast.success('Discovery started — users will appear in a few minutes');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start discovery';
      toast.error(msg);
    }
  };

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <LoadingSpinner size="lg" label="Loading..." />
    </div>
  );
  if (isError || !product) return <ErrorState title="Failed to load product" />;

  const currentStatus = status ?? product;
  const isPipelineComplete = ['ranked', 'completed'].includes(currentStatus.status);

  // ── Discovery sources ────────────────────────────────────────────────────────
  // Stat-card count: jobs.users_discovered is always reliable
  const totalDiscovered = (jobs ?? [])
    .filter(j => j.status === 'completed')
    .reduce((a, j) => a + j.users_discovered, 0);

  // Chart: only platforms with COUNT(*) > 0 in discovered_users table.
  // provider_name lists attempted providers — do NOT use it; it includes
  // providers that ran but found 0 users (e.g. Google Reviews with billing off).
  const sourceDonut = (platformStats ?? [])
    .filter(s => s.count > 0)
    .map(s => ({
      name: s.platform.charAt(0).toUpperCase() + s.platform.slice(1),
      value: s.count,
      color: getProviderColor(s.platform),
    }));
  const sourceLabels = sourceDonut.map(s => s.name).join(' · ');

  // ── Real tier counts from API ────────────────────────────────────────────────
  const hotCount = matchStatus?.hot ?? 0;
  const warmCount = matchStatus?.warm ?? 0;
  const coldCount = matchStatus?.cold ?? 0;
  const tierDonut = [
    { name: 'Hot',  value: hotCount,  color: '#dc2626' },
    { name: 'Warm', value: warmCount, color: '#ea580c' },
    { name: 'Cold', value: coldCount, color: '#3b82f6' },
  ].filter(d => d.value > 0);

  // ── Top lead ─────────────────────────────────────────────────────────────────
  const topLead = leadsData?.leads?.[0];
  const topScore = topLead
    ? `${topLead.final_score.toFixed(0)}%`
    : '—';
  const topLeadSub = topLead
    ? `${topLead.display_name ?? topLead.username} · ${topLead.platform}`
    : 'No leads yet';

  // ── OCEAN scoring model ──────────────────────────────────────────────────────
  const oceanScored = oceanStatus?.ocean_scored ?? 0;
  const scoringModel = oceanStatus?.scoring_model ?? 'Ollama';

  // ── Motivation category percentages (real counts from analytics) ─────────────
  const topCats = analytics?.top_motivation_categories ?? [];
  const totalCatLeads = topCats.reduce((s, c) => s + c.count, 0);
  const motivationBars = topCats.slice(0, 5).map(c => ({
    name: c.category,
    pct: totalCatLeads > 0 ? Math.round((c.count / totalCatLeads) * 100) : 0,
  }));

  // Fallback: if analytics not yet available, use sort_order weights
  const cats = motivations?.categories ?? [];
  const fallbackBars = cats.slice(0, 5).map((cat, i) => {
    const n = cats.length;
    const pct = n > 0 ? Math.round(((n - i) / (n * (n + 1) / 2)) * 100) : 0;
    return { name: cat.name, pct };
  });
  const displayBars = motivationBars.length > 0 ? motivationBars : fallbackBars;

  // ── Pipeline activity from jobs ──────────────────────────────────────────────
  const activity = (jobs ?? [])
    .filter(j => j.completed_at || j.started_at)
    .sort((a, b) =>
      (b.completed_at ?? b.started_at ?? '').localeCompare(a.completed_at ?? a.started_at ?? '')
    )
    .slice(0, 8);

  // True when a discovery job is already active — suppresses the Start Discovery button.
  const hasActiveDiscoveryJob = (jobs ?? []).some(
    j => ['pending', 'running', 'collecting'].includes(j.status)
  );

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Campaign Overview</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {product.name}
            {(product.target_location ?? product.target_city) ? ` · ${product.target_location ?? product.target_city}` : ''}
            {product.category ? ` · ${product.category}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {currentStatus.status === 'similar_products_found' && (
            hasActiveDiscoveryJob ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold rounded-lg">
                <LoadingSpinner size="sm" />
                Discovery running...
              </div>
            ) : (
              <button
                onClick={handleStartDiscovery}
                disabled={startingDisc}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
              >
                {startingDisc ? <LoadingSpinner size="sm" /> : <Search size={13} />}
                Start Discovery
              </button>
            )
          )}
          {currentStatus.status === 'failed' && (
            <button
              onClick={handleRestart}
              disabled={restarting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
            >
              <RotateCcw size={13} className={restarting ? 'animate-spin' : ''} />
              Restart Pipeline
            </button>
          )}
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${
            isPipelineComplete
              ? 'bg-green-50 text-green-700 border border-green-200'
              : currentStatus.status === 'failed'
              ? 'bg-red-50 text-red-700 border border-red-200'
              : 'bg-amber-50 text-amber-700 border border-amber-200'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              isPipelineComplete ? 'bg-green-500'
              : currentStatus.status === 'failed' ? 'bg-red-500'
              : 'bg-amber-400'
            }`} />
            {isPipelineComplete
              ? 'Pipeline Complete'
              : currentStatus.status.replace(/_/g, ' ')}
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="USERS DISCOVERED"
          value={totalDiscovered.toString()}
          sub={sourceLabels || 'No sources yet'}
          color="text-slate-800"
        />
        <StatCard
          label="OCEAN SCORED"
          value={oceanScored.toString()}
          sub={`via ${scoringModel}`}
          color="text-slate-800"
        />
        <StatCard
          label="HOT LEADS"
          value={String(hotCount)}
          sub="Score > 75% match"
          color="text-red-600"
        />
        <StatCard
          label="TOP MATCH SCORE"
          value={topScore}
          sub={topLeadSub}
          color="text-indigo-600"
        />
      </div>

      {/* Generated keywords — read-only, shown once AI has populated them */}
      {product.keywords && product.keywords.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
            AI-Generated Keywords
          </p>
          <div className="flex flex-wrap gap-1.5">
            {product.keywords.map((kw) => (
              <span
                key={kw}
                className="px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Discovery Sources — fully dynamic */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-700 mb-4">Discovery Sources</h3>
          {sourceDonut.length > 0 ? (
            <DonutChart data={sourceDonut} />
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">
              No discoveries yet
            </div>
          )}
        </div>

        {/* Lead Tier Distribution — real counts */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-700 mb-4">Lead Tier Distribution</h3>
          {tierDonut.length > 0 ? (
            <DonutChart data={tierDonut} />
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">
              No leads ranked yet
            </div>
          )}
        </div>

        {/* Top Motivation Categories — real percentages from analytics */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-700 mb-4">Top Motivation Categories</h3>
          {displayBars.length > 0 ? (
            <div className="space-y-3">
              {displayBars.map(({ name, pct }) => (
                <div key={name}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-600 truncate max-w-[140px]">{name}</span>
                    <span className="text-slate-500 font-medium shrink-0 ml-2">{pct}%</span>
                  </div>
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">
              No motivations yet
            </div>
          )}
        </div>
      </div>

      {/* Pipeline Activity */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <h3 className="font-semibold text-slate-700 mb-4">Pipeline Activity Log</h3>
        {activity.length === 0 ? (
          <p className="text-sm text-slate-400">No activity yet.</p>
        ) : (
          <div className="space-y-2">
            {activity.map((job) => (
              <div key={job.id} className="flex items-center gap-3 py-1.5 border-b border-slate-50 last:border-0">
                <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
                  job.status === 'completed' ? 'bg-green-50 text-green-700' :
                  job.status === 'failed'    ? 'bg-red-50 text-red-700' :
                  'bg-amber-50 text-amber-700'
                }`}>
                  {job.status === 'completed' ? 'OK' : job.status.toUpperCase()}
                </span>
                <span className="text-sm text-slate-600">
                  Discovery via <span className="font-medium capitalize">{job.provider_name}</span>
                  {job.status === 'completed' ? ` — ${job.users_discovered} users found` : ''}
                </span>
                <span className="text-xs text-slate-400 ml-auto shrink-0">
                  {job.completed_at ? new Date(job.completed_at).toLocaleTimeString() : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string; sub: string; color: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-slate-400 mt-1.5">{sub}</p>
    </div>
  );
}
