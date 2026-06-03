'use client';

import { X, ExternalLink, MapPin, Users } from 'lucide-react';
import { PlatformBadge } from '@/components/shared/PlatformBadge';
import { OceanBars } from '@/components/charts/OceanBars';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { useUserContent, useUserNlp, useUserOcean } from '@/lib/hooks/useDiscovery';
import { formatNumber, formatDate, getInitials } from '@/lib/utils';
import type { DiscoveredUser } from '@/lib/types/api';

interface UserDetailModalProps {
  user: DiscoveredUser;
  productId: string;
  onClose: () => void;
}

export function UserDetailModal({ user, productId, onClose }: UserDetailModalProps) {
  const { data: content, isLoading: contentLoading } = useUserContent(productId, user.id);
  const { data: nlp } = useUserNlp(productId, user.id);
  const { data: ocean } = useUserOcean(productId, user.id);
  const initials = getInitials(user.display_name ?? user.username);

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-lg bg-white shadow-xl overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-slate-200 sticky top-0 bg-white z-10">
          <h2 className="font-semibold text-slate-800">User Details</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded transition">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Header */}
          <div className="flex items-start gap-3">
            <div className="w-12 h-12 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold shrink-0">
              {initials}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-800">
                  {user.display_name ?? user.username}
                </h3>
                <PlatformBadge platform={user.platform} />
              </div>
              <p className="text-sm text-slate-500">@{user.username}</p>
              <div className="flex items-center gap-3 mt-1">
                {user.follower_count !== undefined && (
                  <span className="flex items-center gap-1 text-xs text-slate-500">
                    <Users size={11} />
                    {formatNumber(user.follower_count)} followers
                  </span>
                )}
                {user.location && (
                  <span className="flex items-center gap-1 text-xs text-slate-500">
                    <MapPin size={11} />
                    {user.location}
                  </span>
                )}
              </div>
              {user.profile_url && (
                <a
                  href={user.profile_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-xs text-indigo-600 hover:underline mt-1"
                >
                  View Profile <ExternalLink size={10} />
                </a>
              )}
            </div>
          </div>

          {user.bio && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1">Bio</p>
              <p className="text-sm text-slate-600">{user.bio}</p>
            </div>
          )}

          {/* OCEAN */}
          {ocean && (
            <div className="bg-slate-50 rounded-lg p-4">
              <p className="text-xs font-semibold text-slate-400 uppercase mb-3">OCEAN Profile</p>
              <OceanBars
                data={{
                  openness: ocean.openness,
                  conscientiousness: ocean.conscientiousness,
                  extraversion: ocean.extraversion,
                  agreeableness: ocean.agreeableness,
                  neuroticism: ocean.neuroticism,
                }}
              />
              <p className="text-xs text-slate-400 mt-2">
                Confidence: {Math.round(ocean.confidence * 100)}% · Method: {ocean.scoring_method}
              </p>
            </div>
          )}

          {/* NLP */}
          {nlp && nlp.interest_tags.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Interest Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {nlp.interest_tags.map((tag) => (
                  <span key={tag} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Content */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Recent Content</p>
            {contentLoading ? (
              <LoadingSpinner size="sm" />
            ) : content?.length ? (
              <ul className="space-y-2">
                {content.slice(0, 5).map((c) => (
                  <li
                    key={c.id}
                    className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3"
                  >
                    <p className="line-clamp-3">{c.content_text}</p>
                    <p className="text-xs text-slate-400 mt-1">{formatDate(c.collected_at)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-400">No content collected</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
