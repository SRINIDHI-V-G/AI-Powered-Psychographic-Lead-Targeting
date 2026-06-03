'use client';

interface CategoryBarProps {
  categories: Array<{ category: string; count: number }>;
}

export function MotivationCategoryBars({ categories }: CategoryBarProps) {
  if (!categories.length) {
    return <p className="text-sm text-slate-400 py-4 text-center">No categories</p>;
  }
  const max = Math.max(...categories.map((c) => c.count), 1);
  return (
    <ul className="space-y-2">
      {categories.slice(0, 6).map(({ category, count }) => {
        const pct = Math.round((count / max) * 100);
        return (
          <li key={category} className="space-y-0.5">
            <div className="flex justify-between text-xs text-slate-600">
              <span className="truncate max-w-[160px]">{category}</span>
              <span className="font-semibold ml-2">{count}</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full"
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
