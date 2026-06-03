'use client';

import { X, ExternalLink, MapPin, Users } from 'lucide-react';
import { TierBadge } from '@/components/shared/TierBadge';
import { PlatformBadge } from '@/components/shared/PlatformBadge';
import { OceanBars } from '@/components/charts/OceanBars';
import { ScoreBar } from '@/components/charts/ScoreBar';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { useLeadDetail } from '@/lib/hooks/useLeads';
import { useUserOcean } from '@/lib/hooks/useDiscovery';
import { formatNumber, getInitials, getTier } from '@/lib/utils';
import type { Lead } from '@/lib/types/api';

interface LeadDetailModalProps {
  lead: Lead;
  productId: string;
  onClose: () => void;
}

export function LeadDetailModal({ lead, productId, onClose }: LeadDetailModalProps) {
  const { data: detail, isLoading } = useLeadDetail(productId, lead.user_id);
  const { data: ocean } = useUserOcean(productId, lead.user_id);
  const initials = getInitials(lead.display_name ?? lead.username);
  const tier = getTier(lead.final_score);

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-lg bg-white shadow-xl overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-slate-200 sticky top-0 bg-white z-10">
          <h2 className="font-semibold text-slate-800">Lead Details</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded transition">
            <X size={18} />
          </button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <LoadingSpinner label="Loading lead details..." />
          </div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Header */}
            <div className="flex items-start gap-3">
              <div className="relative">
                <div className="w-12 h-12 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold">
                  {initials}
                </div>
                <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-white border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-700">
                  {lead.rank}
                </div>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold text-slate-800">
                    {lead.display_name ?? lead.username}
                  </h3>
                  <PlatformBadge platform={lead.platform} />
                  <TierBadge score={lead.final_score} />
                </div>
                <p className="text-sm text-slate-500">@{lead.username}</p>
                <div className="flex items-center gap-3 mt-1">
                  {lead.follower_count !== undefined && (
                    <span className="flex items-center gap-1 text-xs text-slate-500">
                      <Users size={11} />
                      {formatNumber(lead.follower_count)}
                    </span>
                  )}
                  {lead.location && (
                    <span className="flex items-center gap-1 text-xs text-slate-500">
                      <MapPin size={11} />
                      {lead.location}
                    </span>
                  )}
                </div>
                {lead.profile_url && (
                  <a
                    href={lead.profile_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:underline mt-1"
                  >
                    View Profile <ExternalLink size={10} />
                  </a>
                )}
              </div>
            </div>

            {/* Score Breakdown */}
            <div className="bg-slate-50 rounded-lg p-4 space-y-3">
              <p className="text-xs font-semibold text-slate-400 uppercase">Score Breakdown</p>
              <ScoreBar label="Compatibility Score" value={lead.final_score} color="#6366f1" />
              <ScoreBar label="Personality Match (OCEAN)" value={lead.ocean_score} color="#0891b2" />
              <ScoreBar label="Interest Match" value={lead.interest_score} color="#f59e0b" />
              <ScoreBar label="Activity Score" value={lead.embedding_score} color="#10b981" />
              <ScoreBar
                label="LLM Confidence"
                value={lead.confidence * 100}
                color="#8b5cf6"
              />
            </div>

            {/* Best motivation */}
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1">
                Best Motivation Category
              </p>
              <p className="text-sm font-medium text-indigo-700 bg-indigo-50 px-3 py-2 rounded-lg">
                {lead.best_motivation_category}
              </p>
            </div>

            {/* Reasoning */}
            {lead.reasoning.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Reasoning</p>
                <ul className="space-y-1.5">
                  {lead.reasoning.map((r, i) => (
                    <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                      <span className="text-indigo-400 mt-0.5">•</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* OCEAN */}
            {ocean && (
              <div className="bg-slate-50 rounded-lg p-4">
                <p className="text-xs font-semibold text-slate-400 uppercase mb-3">
                  OCEAN Profile
                </p>
                <OceanBars
                  data={{
                    openness: ocean.openness,
                    conscientiousness: ocean.conscientiousness,
                    extraversion: ocean.extraversion,
                    agreeableness: ocean.agreeableness,
                    neuroticism: ocean.neuroticism,
                  }}
                />
              </div>
            )}

            {/* All category scores */}
            {detail?.all_category_scores && detail.all_category_scores.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase mb-2">
                  All Category Scores
                </p>
                <ul className="space-y-2">
                  {detail.all_category_scores.map((cat) => (
                    <li
                      key={cat.motivation_category_id}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-slate-600 truncate max-w-[200px]">
                        {cat.motivation_category}
                      </span>
                      <span className="font-semibold text-indigo-600 ml-2">
                        {(cat.final_score / 10).toFixed(1)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
