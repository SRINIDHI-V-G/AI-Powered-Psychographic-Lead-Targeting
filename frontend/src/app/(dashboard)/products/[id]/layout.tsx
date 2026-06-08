import { ProductSidebar } from '@/components/layout/ProductSidebar';

export default function ProductLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  return (
    <div className="flex flex-1 overflow-hidden">
      <ProductSidebar productId={params.id} />
      <main className="flex-1 overflow-y-auto p-6">
        {children}
      </main>
    </div>
  );
}
