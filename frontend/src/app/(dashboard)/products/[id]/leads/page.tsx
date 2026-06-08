'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { useLeads, useMatchStatus } from '@/lib/hooks/useLeads';
import { LeadDetailModal } from '@/components/leads/LeadDetailModal';
import { Pagination } from '@/components/shared/Pagination';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { downloadWithAuth } from '@/lib/api/client';
import { getInitials, getTier } from '@/lib/utils';
import type { Lead } from '@/lib/types/api';

const AVATAR_COLORS = [
  'bg-indigo-500', 'bg-cyan-500', 'bg-amber-500', 'bg-emerald-500', 'bg-pink-500',
];
function avatarColor(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

const TIER_STYLE: Record<string, { badge: string; bar: string }> = {
  Hot:  { badge: 'bg-red-100 text-red-700 border-red-200',         bar: '#dc2626' },
  Warm: { badge: 'bg-orange-100 text-orange-700 border-orange-200', bar: '#ea580c' },
  Cold: { badge: 'bg-blue-100 text-blue-700 border-blue-200',       bar: '#3b82f6' },
};

const MOTIVATION_COLORS = [
  'bg-indigo-50 text-indigo-700', 'bg-cyan-50 text-cyan-700',
  'bg-purple-50 text-purple-700', 'bg-emerald-50 text-emerald-700',
  'bg-pink-50 text-pink-700',
];

const OCEAN_DIMS = ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism'] as const;
const OCEAN_COLORS = ['#6366f1', '#6366f1', '#6366f1', '#6366f1', '#6366f1'];

export default function LeadsPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const { data: matchStatus } = useMatchStatus(id);
  const { data, isLoading, isError, refetch } = useLeads(id, {
    page,
    page_size: 25,
    sort: 'top',
  });

  // Real tier counts from API (not from page slice)
  const hotCount  = matchStatus?.hot  ?? 0;
  const warmCount = matchStatus?.warm ?? 0;
  const coldCount = matchStatus?.cold ?? 0;

  const displayed = search
    ? (data?.leads ?? []).filter(l => {
        const q = search.toLowerCase();
        return (
          l.username.toLowerCase().includes(q) ||
          (l.display_name ?? '').toLowerCase().includes(q) ||
          (l.location ?? '').toLowerCase().includes(q) ||
          l.best_motivation_category.toLowerCase().includes(q)
        );
      })
    : (data?.leads ?? []);

  // Assign stable colors to motivation categories
  const motivColorMap: Record<string, string> = {};
  let colorIdx = 0;
  displayed.forEach(l => {
    if (!motivColorMap[l.best_motivation_category]) {
      motivColorMap[l.best_motivation_category] = MOTIVATION_COLORS[colorIdx++ % MOTIVATION_COLORS.length];
    }
  });

  const handleExport = async () => {
    try {
      const url = `/api/v1/products/${id}/leads/export?format=csv`;
      await downloadWithAuth(url, `leads-${id}.csv`);
      toast.success('Exported as CSV');
    } catch { toast.error('Export failed'); }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Lead Rankings</h1>
          <p className="text-sm text-slate-500 mt-0.5">Ranked by psychographic compatibility score</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Real tier counts from API */}
          {hotCount  > 0 && <span className="px-2.5 py-1 bg-red-50 text-red-700 text-xs font-semibold rounded-full border border-red-200">{hotCount} Hot</span>}
          {warmCount > 0 && <span className="px-2.5 py-1 bg-orange-50 text-orange-700 text-xs font-semibold rounded-full border border-orange-200">{warmCount} Warm</span>}
          {coldCount > 0 && <span className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-semibold rounded-full border border-blue-200">{coldCount} Cold</span>}
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 text-xs font-medium rounded-lg hover:bg-slate-50 transition"
          >
            <Download size={12} /> CSV
          </button>
        </div>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search leads..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full max-w-sm px-4 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner size="lg" label="Loading leads..." />
        </div>
      ) : isError ? (
        <ErrorState title="Failed to load leads" onRetry={() => void refetch()} />
      ) : !displayed.length ? (
        <EmptyState title="No leads found" description="Matching hasn't completed yet or no leads match." />
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide w-16">Rank</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Lead</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden md:table-cell">Best Motivation</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide w-40">Match Score</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide w-20">Tier</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden lg:table-cell w-28">OCEAN</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {displayed.map((lead) => {
                const tier = getTier(lead.final_score);
                const ts = TIER_STYLE[tier] ?? TIER_STYLE.Cold;
                const color = avatarColor(lead.username);
                const initials = getInitials(lead.display_name ?? lead.username);
                const motivColor = motivColorMap[lead.best_motivation_category] ?? MOTIVATION_COLORS[0];
                const hasOcean = lead.openness !== undefined && lead.openness !== null;

                return (
                  <tr
                    key={lead.user_id}
                    onClick={() => setSelectedLead(lead)}
                    className="cursor-pointer hover:bg-indigo-50/40 transition"
                  >
                    {/* Rank */}
                    <td className="py-3.5 px-4">
                      <div className="w-8 h-8 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">
                        #{lead.rank}
                      </div>
                    </td>

                    {/* Lead */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2.5">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0 ${color}`}>
                          {initials}
                        </div>
                        <div>
                          <div className="font-medium text-slate-800 text-sm">
                            {lead.display_name ?? lead.username}
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5">
                            {lead.location ? `@${lead.username} · ${lead.location}` : `@${lead.username}`}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Best motivation — colored pill */}
                    <td className="py-3.5 px-4 hidden md:table-cell">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${motivColor}`}>
                        {lead.best_motivation_category}
                      </span>
                    </td>

                    {/* Score */}
                    <td className="py-3.5 px-4">
                      <div className="space-y-1">
                        <span className="font-bold text-sm" style={{ color: ts.bar }}>
                          {lead.final_score.toFixed(0)}%
                        </span>
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden w-28">
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${lead.final_score}%`, backgroundColor: ts.bar }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Tier */}
                    <td className="py-3.5 px-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${ts.badge}`}>
                        {tier}
                      </span>
                    </td>

                    {/* OCEAN mini bars */}
                    <td className="py-3.5 px-4 hidden lg:table-cell">
                      {hasOcean ? (
                        <div className="flex items-end gap-0.5 h-8">
                          {OCEAN_DIMS.map((dim, i) => {
                            const val = (lead[dim] as number | undefined) ?? 50;
                            const h = Math.max(4, Math.round((val / 100) * 24));
                            return (
                              <div
                                key={dim}
                                className="w-3 rounded-sm"
                                style={{ height: h, backgroundColor: OCEAN_COLORS[i], opacity: 0.85 }}
                                title={`${dim.charAt(0).toUpperCase()}: ${(val / 10).toFixed(1)}`}
                              />
                            );
                          })}
                        </div>
                      ) : (
                        <div className="flex items-end gap-0.5 h-8">
                          {[0.5, 0.6, 0.4, 0.7, 0.3].map((r, i) => (
                            <div key={i} className="w-3 rounded-sm bg-slate-200" style={{ height: Math.round(r * 24) }} />
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total_pages > 1 && (
        <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />
      )}

      {selectedLead && (
        <LeadDetailModal lead={selectedLead} productId={id} onClose={() => setSelectedLead(null)} />
      )}
    </div>
  );
}
