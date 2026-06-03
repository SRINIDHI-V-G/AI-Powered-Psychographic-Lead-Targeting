'use client';

import Link from 'next/link';
import { Plus } from 'lucide-react';
import { useProducts } from '@/lib/hooks/useProducts';
import { ProductCard } from '@/components/products/ProductCard';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';

export default function ProductsPage() {
  const { data: products, isLoading, isError, refetch } = useProducts();

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Products</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage your lead targeting campaigns
          </p>
        </div>
        <Link
          href="/products/new"
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition"
        >
          <Plus size={16} />
          New Product
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner size="lg" label="Loading products..." />
        </div>
      ) : isError ? (
        <ErrorState
          title="Failed to load products"
          onRetry={() => void refetch()}
        />
      ) : !products?.length ? (
        <EmptyState
          title="No products yet"
          description="Create your first product to start the AI targeting pipeline"
          action={
            <Link
              href="/products/new"
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition"
            >
              Create Product
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}
