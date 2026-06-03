'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { useLeads } from '@/lib/hooks/useLeads';
import { LeadTable } from '@/components/leads/LeadTable';
import { LeadFilters } from '@/components/leads/LeadFilters';
import { LeadDetailModal } from '@/components/leads/LeadDetailModal';
import { Pagination } from '@/components/shared/Pagination';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { downloadWithAuth } from '@/lib/api/client';
import type { Lead } from '@/lib/types/api';

interface FiltersState {
  minScore: number;
  minConfidence: number;
  sort: 'top' | 'bottom';
  search: string;
}

export default function LeadsPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FiltersState>({
    minScore: 0,
    minConfidence: 0,
    sort: 'top',
    search: '',
  });
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const { data, isLoading, isError, refetch } = useLeads(id, {
    page,
    page_size: 25,
    min_score: filters.minScore,
    min_confidence: filters.minConfidence,
    sort: filters.sort,
  });

  const updateFilters = (partial: Partial<FiltersState>) => {
    setFilters((prev) => ({ ...prev, ...partial }));
    setPage(1);
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const url = `/api/v1/products/${id}/leads/export?format=${format}&min_score=${filters.minScore}&min_confidence=${filters.minConfidence}`;
      await downloadWithAuth(url, `leads-${id}.${format}`);
      toast.success(`Exported as ${format.toUpperCase()}`);
    } catch {
      toast.error('Export failed');
    }
  };

  const displayedLeads = filters.search
    ? (data?.leads ?? []).filter((l) => {
        const q = filters.search.toLowerCase();
        return (
          l.username.toLowerCase().includes(q) ||
          (l.display_name ?? '').toLowerCase().includes(q) ||
          (l.location ?? '').toLowerCase().includes(q) ||
          l.best_motivation_category.toLowerCase().includes(q)
        );
      })
    : data?.leads ?? [];

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Lead Rankings</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data ? `${data.total_leads} ranked leads` : 'Loading...'}
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 text-sm font-medium rounded-lg hover:bg-slate-50 transition"
          >
            <Download size={14} />
            CSV
          </button>
          <button
            onClick={() => handleExport('json')}
            className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 text-sm font-medium rounded-lg hover:bg-slate-50 transition"
          >
            <Download size={14} />
            JSON
          </button>
        </div>
      </div>

      <LeadFilters filters={filters} onChange={updateFilters} />

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner size="lg" label="Loading leads..." />
        </div>
      ) : isError ? (
        <ErrorState title="Failed to load leads" onRetry={() => void refetch()} />
      ) : !displayedLeads.length ? (
        <EmptyState
          title="No leads found"
          description="The pipeline hasn't reached the ranking stage yet, or no leads match the filters."
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <LeadTable
            leads={displayedLeads}
            onLeadClick={setSelectedLead}
            selectedLeadId={selectedLead?.user_id}
          />
        </div>
      )}

      {data && data.total_pages > 1 && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          onPageChange={setPage}
        />
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
