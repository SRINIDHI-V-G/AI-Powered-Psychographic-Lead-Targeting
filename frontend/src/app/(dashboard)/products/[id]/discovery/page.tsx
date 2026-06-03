'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';
import { useDiscoveredUsers } from '@/lib/hooks/useDiscovery';
import { UserCard } from '@/components/users/UserCard';
import { UserDetailModal } from '@/components/users/UserDetailModal';
import { Pagination } from '@/components/shared/Pagination';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import type { DiscoveredUser } from '@/lib/types/api';

export default function DiscoveryPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [page, setPage] = useState(1);
  const [platformFilter, setPlatformFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedUser, setSelectedUser] = useState<DiscoveredUser | null>(null);

  const { data, isLoading, isError, refetch } = useDiscoveredUsers(id, {
    page,
    limit: 24,
  });

  const filtered = (data?.users ?? []).filter((u) => {
    if (platformFilter && u.platform.toLowerCase() !== platformFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        u.username.toLowerCase().includes(q) ||
        (u.display_name ?? '').toLowerCase().includes(q) ||
        (u.bio ?? '').toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Discovered Users</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {data ? `${data.total} users discovered` : 'Loading...'}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-48"
          />
        </div>
        <select
          value={platformFilter}
          onChange={(e) => setPlatformFilter(e.target.value)}
          className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Platforms</option>
          <option value="instagram">Instagram</option>
          <option value="reddit">Reddit</option>
          <option value="twitter">Twitter</option>
          <option value="mock">Mock</option>
        </select>
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
          description="Discovery hasn't run yet or no users match the filter."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((user) => (
            <UserCard
              key={user.id}
              user={user}
              selected={selectedUser?.id === user.id}
              onClick={() => setSelectedUser(user)}
            />
          ))}
        </div>
      )}

      {data && data.total > 24 && (
        <Pagination
          page={page}
          totalPages={Math.ceil(data.total / 24)}
          onPageChange={setPage}
        />
      )}

      {selectedUser && (
        <UserDetailModal
          user={selectedUser}
          productId={id}
          onClose={() => setSelectedUser(null)}
        />
      )}
    </div>
  );
}
