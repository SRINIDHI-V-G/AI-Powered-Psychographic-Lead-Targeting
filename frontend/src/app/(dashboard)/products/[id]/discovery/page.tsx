'use client';

import { useState } from 'react';
import { useLeads } from '@/lib/hooks/useLeads';
import { useDiscoveryJobs } from '@/lib/hooks/useDiscovery';
import { Pagination } from '@/components/shared/Pagination';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { LeadDetailModal } from '@/components/leads/LeadDetailModal';
import { getInitials, getTier } from '@/lib/utils';
import type { Lead } from '@/lib/types/api';

const PLATFORM_COLORS: Record<string, string> = {
  reddit: 'bg-orange-100 text-orange-700',
  instagram: 'bg-pink-100 text-pink-700',
  youtube: 'bg-red-100 text-red-700',
  twitter: 'bg-sky-100 text-sky-700',
  mock: 'bg-slate-100 text-slate-600',
};

const AVATAR_COLORS = [
  'bg-indigo-500', 'bg-cyan-500', 'bg-amber-500',
  'bg-emerald-500', 'bg-pink-500', 'bg-purple-500',
];

function avatarColor(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

const TIER_STYLE: Record<string, string> = {
  Hot: 'bg-red-100 text-red-700',
  Warm: 'bg-orange-100 text-orange-700',
  Cold: 'bg-blue-100 text-blue-700',
};

const OCEAN_DIMS = [
  { key: 'openness' as keyof Lead, label: 'O', color: '#6366f1' },
  { key: 'conscientiousness' as keyof Lead, label: 'C', color: '#0891b2' },
  { key: 'extraversion' as keyof Lead, label: 'E', color: '#f59e0b' },
  { key: 'agreeableness' as keyof Lead, label: 'A', color: '#10b981' },
  { key: 'neuroticism' as keyof Lead, label: 'N', color: '#ef4444' },
];

export default function DiscoveryPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [page, setPage] = useState(1);
  const [platformFilter, setPlatformFilter] = useState('');
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const { data: jobs } = useDiscoveryJobs(id);
  const { data, isLoading, isError, refetch } = useLeads(id, {
    page,
    page_size: 10,
    sort: 'top',
  });

  // Provider counts from jobs
  const providerCounts: Record<string, number> = {};
  (jobs ?? []).forEach(j => {
    if (j.status === 'completed' && j.provider_name) {
      providerCounts[j.provider_name] = (providerCounts[j.provider_name] ?? 0) + j.users_discovered;
    }
  });
  const totalDiscovered = Object.values(providerCounts).reduce((a, b) => a + b, 0);

  const filtered = platformFilter
    ? (data?.leads ?? []).filter(l => l.platform.toLowerCase() === platformFilter)
    : (data?.leads ?? []);

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Discovered Users</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {totalDiscovered} public profiles discovered
            {data ? ` · Top ${Math.min(data.total_leads, page * 10)} shown` : ''}
          </p>
        </div>
        {/* Platform pills */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setPlatformFilter('')}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
              !platformFilter ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All
          </button>
          {Object.entries(providerCounts).map(([provider, count]) => (
            <button
              key={provider}
              onClick={() => setPlatformFilter(provider === platformFilter ? '' : provider)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                platformFilter === provider
                  ? 'bg-slate-800 text-white'
                  : `${PLATFORM_COLORS[provider] ?? 'bg-slate-100 text-slate-600'} hover:opacity-80`
              }`}
            >
              {provider.charAt(0).toUpperCase() + provider.slice(1)} {count}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner size="lg" label="Loading users..." />
        </div>
      ) : isError ? (
        <ErrorState title="Failed to load users" onRetry={() => void refetch()} />
      ) : !filtered.length ? (
        <EmptyState
          title="No users found"
          description="Discovery hasn't run yet or matching is pending."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((lead) => (
            <LeadUserCard
              key={lead.user_id}
              lead={lead}
              onClick={() => setSelectedLead(lead)}
            />
          ))}
        </div>
      )}

      {data && data.total_pages > 1 && (
        <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />
      )}

      {selectedLead && (
        <LeadDetailModal
          lead={selectedLead}
          productId={id}
          onClose={() => setSelectedLead(null)}
        />
      )}
    </div>
  );
}

function LeadUserCard({ lead, onClick }: { lead: Lead; onClick: () => void }) {
  const initials = getInitials(lead.display_name ?? lead.username);
  const color = avatarColor(lead.username);
  const tier = getTier(lead.final_score);
  const hasOcean = lead.openness !== undefined && lead.openness !== null;

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white rounded-2xl border border-slate-200 p-5 hover:border-indigo-300 hover:shadow-sm transition"
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0 ${color}`}>
            {initials}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-800 text-sm">
                {lead.display_name ?? lead.username}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-bold ${TIER_STYLE[tier] ?? 'bg-slate-100 text-slate-600'}`}>
                {tier.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-xs text-slate-500">@{lead.username}</span>
              <span className="text-slate-300">·</span>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${PLATFORM_COLORS[lead.platform] ?? 'bg-slate-100 text-slate-600'}`}>
                {lead.platform}
              </span>
            </div>
          </div>
        </div>
        <div className="text-right shrink-0">
          <span className={`text-2xl font-bold ${
            tier === 'Hot' ? 'text-red-600' : tier === 'Warm' ? 'text-orange-500' : 'text-blue-500'
          }`}>
            {lead.final_score.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Location + followers */}
      {(lead.location || lead.follower_count !== undefined) && (
        <div className="flex items-center gap-3 mb-3 text-xs text-slate-500">
          {lead.follower_count !== undefined && (
            <span>{(lead.follower_count / 1000).toFixed(1)}k followers</span>
          )}
          {lead.location && <span>{lead.location}</span>}
        </div>
      )}

      {/* OCEAN bars */}
      {hasOcean && (
        <div className="space-y-1.5 mt-3 pt-3 border-t border-slate-100">
          {OCEAN_DIMS.map(({ key, label, color: barColor }) => {
            const val = (lead[key] as number | undefined) ?? 50;
            const display = (val / 10).toFixed(1);
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="text-xs font-bold w-4 text-slate-500">{label}</span>
                <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${val}%`, backgroundColor: barColor }}
                  />
                </div>
                <span className="text-xs text-slate-500 w-6 text-right">{display}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Motivation match */}
      <div className="mt-3 pt-2.5 border-t border-slate-100">
        <span className="text-xs text-indigo-600 font-medium">{lead.best_motivation_category}</span>
      </div>
    </button>
  );
}
