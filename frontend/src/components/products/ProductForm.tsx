'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useCreateProduct } from '@/lib/hooks/useProducts';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';

const schema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  description: z.string().min(20, 'Description must be at least 20 characters'),
  category: z.string().min(2, 'Category is required'),
  subcategory: z.string().optional(),
  price_range: z.enum(['budget', 'mid_range', 'premium', 'luxury']),
  target_location: z.string().min(1, 'Target location is required'),
  target_city: z.string().optional(),
  target_country: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

export function ProductForm() {
  const router = useRouter();
  const { mutateAsync, isPending } = useCreateProduct();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { price_range: 'mid_range' },
  });

  const onSubmit = async (data: FormData) => {
    try {
      const product = await mutateAsync({
        name: data.name,
        description: data.description,
        category: data.category,
        subcategory: data.subcategory,
        price_range: data.price_range,
        target_location: data.target_location,
        target_city: data.target_city,
        target_country: data.target_country,
      });
      toast.success('Product created! Pipeline starting...');
      router.push(`/products/${product.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create product';
      toast.error(msg);
    }
  };

  const field = (
    id: keyof FormData,
    label: string,
    type: string = 'text',
    placeholder?: string
  ) => (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-1">
        {label}
      </label>
      <input
        id={id}
        type={type}
        placeholder={placeholder}
        {...register(id)}
        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      />
      {errors[id] && (
        <p className="text-xs text-red-500 mt-1">{errors[id]?.message}</p>
      )}
    </div>
  );

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      {field('name', 'Product Name', 'text', 'e.g. Noise-Cancelling Headphones Pro')}

      <div>
        <label htmlFor="description" className="block text-sm font-medium text-slate-700 mb-1">
          Description
        </label>
        <textarea
          id="description"
          rows={3}
          placeholder="Describe your product and its target audience..."
          {...register('description')}
          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
        />
        {errors.description && (
          <p className="text-xs text-red-500 mt-1">{errors.description.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {field('category', 'Category', 'text', 'e.g. Electronics')}
        {field('subcategory', 'Subcategory (optional)', 'text', 'e.g. Audio')}
      </div>

      <div>
        <label htmlFor="price_range" className="block text-sm font-medium text-slate-700 mb-1">
          Price Range
        </label>
        <select
          id="price_range"
          {...register('price_range')}
          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="budget">Budget</option>
          <option value="mid_range">Standard</option>
          <option value="premium">Premium</option>
          <option value="luxury">Luxury</option>
        </select>
      </div>

      <div>
        {field('target_location', 'Target Location', 'text', 'e.g. Chennai, India  or  Mumbai, India  or  Bangalore, India')}
        <p className="text-xs text-slate-400 mt-1">Use "City, Country" format for precise location filtering</p>
      </div>

      <button
        type="submit"
        disabled={isPending}
        className="w-full py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-60 flex items-center justify-center gap-2"
      >
        {isPending ? (
          <>
            <LoadingSpinner size="sm" />
            Creating...
          </>
        ) : (
          'Create Product & Start Pipeline'
        )}
      </button>
    </form>
  );
}
