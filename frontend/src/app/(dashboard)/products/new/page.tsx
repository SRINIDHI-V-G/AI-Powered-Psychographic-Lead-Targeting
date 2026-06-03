import Link from 'next/link';
import { ChevronLeft } from 'lucide-react';
import { ProductForm } from '@/components/products/ProductForm';

export default function NewProductPage() {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <Link
          href="/products"
          className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 transition mb-4"
        >
          <ChevronLeft size={16} />
          Back to Products
        </Link>
        <h1 className="text-2xl font-bold text-slate-800">Create New Product</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Define your product and let AI find the best psychographic leads
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <ProductForm />
      </div>
    </div>
  );
}
