'use client';

import { ExternalLink } from 'lucide-react';
import { TierBadge } from '@/components/shared/TierBadge';
import { PlatformBadge } from '@/components/shared/PlatformBadge';
import { formatNumber, getInitials, getTier } from '@/lib/utils';
import { cn } from '@/lib/utils';
import type { Lead } from '@/lib/types/api';

const OCEAN_DIMS = [
  { key: 'ocean_score', color: '#6366f1', title: 'O' },
];

interface LeadTableProps {
  leads: Lead[];
  onLeadClick: (lead: Lead) => void;
  selectedLeadId?: string;
}

const avatarColors = [
  'bg-indigo-500',
  'bg-cyan-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-pink-500',
];

function avatarColor(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return avatarColors[h % avatarColors.length];
}

export function LeadTable({ leads, onLeadClick, selectedLeadId }: LeadTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider w-12">
              Rank
            </th>
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Lead
            </th>
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider hidden md:table-cell">
              Best Motivation
            </th>
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Score
            </th>
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Tier
            </th>
            <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider hidden lg:table-cell">
              OCEAN
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {leads.map((lead) => {
            const initials = getInitials(lead.display_name ?? lead.username);
            const color = avatarColor(lead.username);
            const tier = getTier(lead.final_score);
            const scorePct = lead.final_score;
            const scoreColor =
              tier === 'Hot' ? '#dc2626' : tier === 'Warm' ? '#ea580c' : '#3b82f6';
            const selected = selectedLeadId === lead.user_id;

            return (
              <tr
                key={lead.user_id}
                onClick={() => onLeadClick(lead)}
                className={cn(
                  'cursor-pointer hover:bg-slate-50 transition',
                  selected && 'bg-indigo-50'
                )}
              >
                <td className="py-3 px-4">
                  <span className="w-7 h-7 rounded-full bg-slate-100 text-slate-600 text-xs font-bold flex items-center justify-center">
                    {lead.rank}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={cn(
                        'w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0',
                        color
                      )}
                    >
                      {initials}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-800 truncate max-w-[120px]">
                          {lead.display_name ?? lead.username}
                        </span>
                        <PlatformBadge platform={lead.platform} />
                      </div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-xs text-slate-500 truncate">
                          {lead.location ?? '@' + lead.username}
                        </span>
                        {lead.profile_url && (
                          <a
                            href={lead.profile_url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-slate-400 hover:text-indigo-600"
                          >
                            <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                      {lead.follower_count !== undefined && (
                        <span className="text-xs text-slate-400">
                          {formatNumber(lead.follower_count)} followers
                        </span>
                      )}
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4 hidden md:table-cell">
                  <span className="text-xs text-slate-600 max-w-[150px] line-clamp-2">
                    {lead.best_motivation_category}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <div className="space-y-1 min-w-[80px]">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold" style={{ color: scoreColor }}>
                        {(lead.final_score / 10).toFixed(1)}
                      </span>
                      <span className="text-slate-400">/10</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${scorePct}%`, backgroundColor: scoreColor }}
                      />
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <TierBadge score={lead.final_score} />
                </td>
                <td className="py-3 px-4 hidden lg:table-cell">
                  <div className="flex gap-0.5">
                    {[lead.ocean_score, lead.embedding_score, lead.interest_score, lead.confidence * 100, lead.final_score].map(
                      (v, i) => {
                        const colors = ['#6366f1', '#0891b2', '#f59e0b', '#10b981', '#ef4444'];
                        const h = Math.round((v / 100) * 12) + 2;
                        return (
                          <div
                            key={i}
                            className="w-3 rounded-sm"
                            style={{ height: h, backgroundColor: colors[i], opacity: 0.8 }}
                            title={['O','C','E','A','N'][i] + ': ' + v.toFixed(0)}
                          />
                        );
                      }
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
