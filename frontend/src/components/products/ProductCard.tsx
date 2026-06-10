'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { getPipelineLabel } from '@/lib/utils';
import type { Product } from '@/lib/types/api';

interface ProductCardProps {
  product: Product;
}

export function ProductCard({ product }: ProductCardProps) {
  const displayStep = Math.min(product.pipeline_step, 9);
  const pct = Math.round((displayStep / 9) * 100);

  return (
    <Link
      href={`/products/${product.id}`}
      className="bg-white rounded-xl border border-slate-200 p-5 hover:border-indigo-300 hover:shadow-sm transition group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-slate-800 truncate group-hover:text-indigo-700 transition">
            {product.name}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">{product.category}</p>
        </div>
        <ChevronRight size={16} className="text-slate-300 shrink-0 mt-1 group-hover:text-indigo-500 transition" />
      </div>

      <p className="text-xs text-slate-500 line-clamp-2 mb-4">{product.description}</p>

      <div className="flex items-center justify-between mb-2">
        <StatusBadge status={product.status} />
        <span className="text-xs text-slate-500">{getPipelineLabel(product.pipeline_step)}</span>
      </div>

      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 mt-1 text-right">Step {displayStep} / 9</p>

      {product.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {product.keywords.slice(0, 3).map((kw) => (
            <span
              key={kw}
              className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full"
            >
              {kw}
            </span>
          ))}
          {product.keywords.length > 3 && (
            <span className="text-xs text-slate-400">+{product.keywords.length - 3}</span>
          )}
        </div>
      )}
    </Link>
  );
}
