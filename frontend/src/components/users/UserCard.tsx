'use client';

import { MapPin, Users } from 'lucide-react';
import { PlatformBadge } from '@/components/shared/PlatformBadge';
import { getInitials, formatNumber } from '@/lib/utils';
import { cn } from '@/lib/utils';
import type { DiscoveredUser } from '@/lib/types/api';

interface UserCardProps {
  user: DiscoveredUser;
  onClick?: () => void;
  selected?: boolean;
}

const avatarColors = [
  'bg-indigo-500',
  'bg-cyan-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-pink-500',
  'bg-purple-500',
];

function getColor(username: string) {
  let hash = 0;
  for (const c of username) hash = (hash * 31 + c.charCodeAt(0)) & 0xffff;
  return avatarColors[hash % avatarColors.length];
}

export function UserCard({ user, onClick, selected }: UserCardProps) {
  const initials = getInitials(user.display_name ?? user.username);
  const color = getColor(user.username);

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left bg-white rounded-xl border p-4 hover:border-indigo-300 hover:shadow-sm transition',
        selected ? 'border-indigo-400 ring-1 ring-indigo-300' : 'border-slate-200'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0',
            color
          )}
        >
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-800 text-sm truncate">
              {user.display_name ?? user.username}
            </span>
            <PlatformBadge platform={user.platform} />
          </div>
          <p className="text-xs text-slate-500 mt-0.5">@{user.username}</p>
          {user.bio && (
            <p className="text-xs text-slate-500 mt-1.5 line-clamp-2">{user.bio}</p>
          )}
          <div className="flex items-center gap-3 mt-2">
            {user.follower_count !== undefined && (
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Users size={10} />
                {formatNumber(user.follower_count)}
              </span>
            )}
            {user.location && (
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <MapPin size={10} />
                {user.location}
              </span>
            )}
          </div>
          <div className="flex gap-1.5 mt-2">
            {user.nlp_processed && (
              <span className="px-1.5 py-0.5 bg-cyan-50 text-cyan-600 text-xs rounded">NLP</span>
            )}
            {user.ocean_scored && (
              <span className="px-1.5 py-0.5 bg-teal-50 text-teal-600 text-xs rounded">OCEAN</span>
            )}
            {user.matched && (
              <span className="px-1.5 py-0.5 bg-green-50 text-green-600 text-xs rounded">Matched</span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}
