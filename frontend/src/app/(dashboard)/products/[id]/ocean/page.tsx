'use client';

import { useLeads } from '@/lib/hooks/useLeads';
import { OceanBars } from '@/components/charts/OceanBars';
import { TierBadge } from '@/components/shared/TierBadge';
import { PlatformBadge } from '@/components/shared/PlatformBadge';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';

export default function OceanProfilesPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data, isLoading, isError, refetch } = useLeads(id, { page: 1, page_size: 50 });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" label="Loading OCEAN profiles..." />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to load OCEAN profiles"
        message="Rankings may not be available yet. Run the full pipeline first."
        onRetry={() => void refetch()}
      />
    );
  }

  const leads = data?.leads ?? [];
  const scored = leads.filter(
    (l) =>
      l.openness !== undefined &&
      l.conscientiousness !== undefined &&
      l.extraversion !== undefined &&
      l.agreeableness !== undefined &&
      l.neuroticism !== undefined
  );

  if (scored.length === 0) {
    return (
      <EmptyState
        title="No OCEAN profiles yet"
        description="OCEAN personality scoring runs after user discovery and NLP processing."
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">OCEAN Profiles</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Personality scores for {scored.length} discovered user{scored.length !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Summary bar */}
      {scored.length > 0 && (() => {
        const avg = (key: 'openness' | 'conscientiousness' | 'extraversion' | 'agreeableness' | 'neuroticism') =>
          Math.round(scored.reduce((s, l) => s + (l[key] ?? 0), 0) / scored.length);
        return (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="font-semibold text-slate-700 mb-4">Audience Average</h2>
            <OceanBars
              data={{
                openness: avg('openness'),
                conscientiousness: avg('conscientiousness'),
                extraversion: avg('extraversion'),
                agreeableness: avg('agreeableness'),
                neuroticism: avg('neuroticism'),
              }}
            />
          </div>
        );
      })()}

      {/* Per-user profiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scored.map((lead) => (
          <div key={lead.user_id} className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="flex items-start justify-between mb-3">
              <div className="min-w-0">
                <p className="font-semibold text-slate-800 text-sm truncate">
                  {lead.display_name || lead.username}
                </p>
                <p className="text-xs text-slate-500 truncate">@{lead.username}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                <PlatformBadge platform={lead.platform} />
                <TierBadge score={lead.final_score} />
              </div>
            </div>
            <OceanBars
              data={{
                openness: lead.openness!,
                conscientiousness: lead.conscientiousness!,
                extraversion: lead.extraversion!,
                agreeableness: lead.agreeableness!,
                neuroticism: lead.neuroticism!,
              }}
              compact={false}
            />
            <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
              <span className="text-xs text-slate-400">
                Method: {lead.ocean_scoring_method ?? 'llm'}
              </span>
              <span className="text-xs font-semibold text-indigo-600">
                Score {(lead.final_score / 10).toFixed(1)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
