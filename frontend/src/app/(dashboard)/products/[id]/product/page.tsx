'use client';

import { Package, MapPin, Tag, DollarSign, Building2 } from 'lucide-react';
import { useProduct } from '@/lib/hooks/useProducts';
import { useCompany } from '@/lib/hooks/useCompany';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { ErrorState } from '@/components/shared/ErrorState';

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  const { data: product, isLoading, isError } = useProduct(params.id);
  const { data: company } = useCompany();

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <LoadingSpinner size="lg" label="Loading product..." />
    </div>
  );
  if (isError || !product) return <ErrorState title="Failed to load product" />;

  const priceLabel: Record<string, string> = {
    budget: 'Budget', mid_range: 'Mid Range', premium: 'Premium', luxury: 'Luxury',
    standard: 'Standard',
  };

  const locationDisplay = [product.target_city, product.target_country]
    .filter(Boolean)
    .join(', ') || product.target_location || '—';

  const companyMeta = [company?.industry, company?.email].filter(Boolean).join(' · ');

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Submitted Product</h1>
        <p className="text-sm text-slate-500 mt-0.5">Product details used to train the targeting pipeline</p>
      </div>

      {/* Product card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <Package size={24} className="text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-slate-800">{product.name}</h2>
            <p className="text-sm text-slate-500 mt-1 leading-relaxed">{product.description}</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Category</span>
            <div className="flex items-center gap-1.5">
              <Tag size={13} className="text-slate-400" />
              <span className="text-sm font-medium text-slate-700">
                {product.category}{product.subcategory ? ` / ${product.subcategory}` : ''}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Price Range</span>
            <div className="flex items-center gap-1.5">
              <DollarSign size={13} className="text-slate-400" />
              <span className="text-sm font-medium text-slate-700">
                {priceLabel[product.price_range] ?? product.price_range}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Target Location</span>
            <div className="flex items-center gap-1.5">
              <MapPin size={13} className="text-slate-400" />
              <span className="text-sm font-medium text-slate-700">{locationDisplay}</span>
            </div>
          </div>
        </div>

        {product.keywords.length > 0 && (
          <div className="mt-5 pt-5 border-t border-slate-100">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Keywords</p>
            <div className="flex flex-wrap gap-1.5">
              {product.keywords.map((kw) => (
                <span key={kw} className="px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full font-medium">
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Company card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Company</p>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center shrink-0">
            <Building2 size={20} className="text-slate-500" />
          </div>
          <div>
            <p className="font-semibold text-slate-800">{company?.name ?? 'Your Company'}</p>
            {companyMeta && (
              <p className="text-xs text-slate-500 mt-0.5">{companyMeta}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
