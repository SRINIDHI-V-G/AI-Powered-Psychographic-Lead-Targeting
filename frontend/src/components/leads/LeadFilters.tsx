'use client';

import { Search } from 'lucide-react';

interface LeadFiltersState {
  minScore: number;
  minConfidence: number;
  sort: 'top' | 'bottom';
  search: string;
}

interface LeadFiltersProps {
  filters: LeadFiltersState;
  onChange: (f: Partial<LeadFiltersState>) => void;
}

export function LeadFilters({ filters, onChange }: LeadFiltersProps) {
  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          placeholder="Search leads..."
          value={filters.search}
          onChange={(e) => onChange({ search: e.target.value })}
          className="pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-44"
        />
      </div>

      <div className="flex items-center gap-1.5 text-sm">
        <label className="text-slate-500 text-xs">Min Score</label>
        <input
          type="number"
          min={0}
          max={100}
          value={filters.minScore}
          onChange={(e) => onChange({ minScore: Number(e.target.value) })}
          className="w-16 px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div className="flex items-center gap-1.5 text-sm">
        <label className="text-slate-500 text-xs">Min Confidence</label>
        <input
          type="number"
          min={0}
          max={1}
          step={0.1}
          value={filters.minConfidence}
          onChange={(e) => onChange({ minConfidence: Number(e.target.value) })}
          className="w-16 px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <select
        value={filters.sort}
        onChange={(e) => onChange({ sort: e.target.value as 'top' | 'bottom' })}
        className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <option value="top">Top Scores</option>
        <option value="bottom">Bottom Scores</option>
      </select>
    </div>
  );
}
