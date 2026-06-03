'use client';

import { RefreshCw, Play, ChevronLeft } from 'lucide-react';
import Link from 'next/link';
import { toast } from 'sonner';
import { useProduct, useProductStatus, useRestartProduct } from '@/lib/hooks/useProducts';
import { useMatchStatus, useTriggerMatch } from '@/lib/hooks/useLeads';
import { useLeadsSummary } from '@/lib/hooks/useAnalytics';
import { useDiscoveryJobs } from '@/lib/hooks/useDiscovery';
import { useNlpStatus } from '@/lib/hooks/useNlpStatus';
import { useOceanStatus } from '@/lib/hooks/useOceanStatus';
import { PipelineProgress } from '@/components/products/PipelineProgress';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { ErrorState } from '@/components/shared/ErrorState';
import { formatNumber, formatDate } from '@/lib/utils';

export default function ProductOverviewPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data: product, isLoading, isError } = useProduct(id);
  const { data: status } = useProductStatus(id);
  const { data: matchStatus } = useMatchStatus(id);
  const { data: summary } = useLeadsSummary(id);
  const { data: jobs } = useDiscoveryJobs(id);
  const { data: nlpStatus } = useNlpStatus(id);
  const { data: oceanStatus } = useOceanStatus(id);
  const { mutateAsync: restart, isPending: restarting } = useRestartProduct(id);
  const { mutateAsync: triggerMatch, isPending: matching } = useTriggerMatch(id);

  const handleRestart = async () => {
    try {
      await restart();
      toast.success('Pipeline restarted');
    } catch {
      toast.error('Failed to restart pipeline');
    }
  };

  const handleTriggerMatch = async () => {
    try {
      await triggerMatch();
      toast.success('Matching triggered');
    } catch {
      toast.error('Failed to trigger matching');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" label="Loading product..." />
      </div>
    );
  }

  if (isError || !product) {
    return <ErrorState title="Failed to load product" />;
  }

  const currentStatus = status ?? product;
  const totalUsers = jobs?.reduce((a, j) => a + j.users_discovered, 0) ?? 0;

  const statsCards = [
    {
      label: 'Users Discovered',
      value: formatNumber(totalUsers),
      color: 'bg-indigo-50 text-indigo-700',
    },
    {
      label: 'NLP Processed',
      value: nlpStatus ? `${nlpStatus.nlp_processed}/${nlpStatus.total_users}` : '—',
      color: 'bg-cyan-50 text-cyan-700',
    },
    {
      label: 'OCEAN Scored',
      value: oceanStatus ? `${oceanStatus.ocean_scored}/${oceanStatus.total_users}` : '—',
      color: 'bg-teal-50 text-teal-700',
    },
    {
      label: 'Leads Ranked',
      value: matchStatus ? formatNumber(matchStatus.ranked) : '—',
      color: 'bg-green-50 text-green-700',
    },
    {
      label: 'Avg Score',
      value: summary ? (summary.avg_score / 10).toFixed(1) : '—',
      color: 'bg-amber-50 text-amber-700',
    },
    {
      label: 'Top Score',
      value: summary ? (summary.top_score / 10).toFixed(1) : '—',
      color: 'bg-purple-50 text-purple-700',
    },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/products"
            className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 transition mb-1"
          >
            <ChevronLeft size={16} />
            All Products
          </Link>
          <h1 className="text-2xl font-bold text-slate-800">{product.name}</h1>
          <div className="flex items-center gap-2 mt-1.5">
            <StatusBadge status={currentStatus.status} />
            <span className="text-xs text-slate-500">{product.category}</span>
            {product.price_range && (
              <span className="text-xs text-slate-500 capitalize">· {product.price_range}</span>
            )}
          </div>
        </div>

        <div className="flex gap-2 shrink-0">
          <button
            onClick={handleTriggerMatch}
            disabled={matching}
            className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
          >
            <Play size={14} />
            Re-run Match
          </button>
          <button
            onClick={handleRestart}
            disabled={restarting}
            className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 text-sm font-medium rounded-lg hover:bg-slate-50 transition disabled:opacity-60"
          >
            <RefreshCw size={14} className={restarting ? 'animate-spin' : ''} />
            Restart
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statsCards.map(({ label, value, color }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-4">
            <p className={`text-xl font-bold ${color.split(' ')[1]}`}>{value}</p>
            <p className="text-xs text-slate-500 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Pipeline */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-700 mb-4">Pipeline Progress</h2>
        <PipelineProgress step={currentStatus.pipeline_step} status={currentStatus.status} />
      </div>

      {/* Description */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-700 mb-3">Product Details</h2>
        <p className="text-sm text-slate-600 mb-4">{product.description}</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          {product.target_location && (
            <div>
              <p className="text-slate-400 uppercase font-semibold">Location</p>
              <p className="text-slate-700 mt-0.5">{product.target_location}</p>
            </div>
          )}
          {product.target_country && (
            <div>
              <p className="text-slate-400 uppercase font-semibold">Country</p>
              <p className="text-slate-700 mt-0.5">{product.target_country}</p>
            </div>
          )}
          <div>
            <p className="text-slate-400 uppercase font-semibold">Created</p>
            <p className="text-slate-700 mt-0.5">{formatDate(product.created_at)}</p>
          </div>
          <div>
            <p className="text-slate-400 uppercase font-semibold">Updated</p>
            <p className="text-slate-700 mt-0.5">{formatDate(product.updated_at)}</p>
          </div>
        </div>
        {product.keywords.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {product.keywords.map((kw) => (
              <span
                key={kw}
                className="px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full font-medium"
              >
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {currentStatus.status === 'failed' && currentStatus.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-sm font-semibold text-red-700 mb-1">Pipeline Failed</p>
          <p className="text-sm text-red-600">{currentStatus.error_message}</p>
        </div>
      )}
    </div>
  );
}
