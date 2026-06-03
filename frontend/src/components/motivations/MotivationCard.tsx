'use client';

import { OceanBars } from '@/components/charts/OceanBars';
import { OceanRadar } from '@/components/charts/OceanRadar';
import type { MotivationCategory } from '@/lib/types/api';

interface MotivationCardProps {
  category: MotivationCategory;
  index: number;
}

export function MotivationCard({ category, index }: MotivationCardProps) {
  const op = category.ocean_profile;
  const oceanData = {
    openness: op.openness,
    conscientiousness: op.conscientiousness,
    extraversion: op.extraversion,
    agreeableness: op.agreeableness,
    neuroticism: 100 - op.emotional_stability,
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-8 h-8 rounded-full bg-indigo-600 text-white text-sm font-bold flex items-center justify-center shrink-0">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-800">{category.name}</h3>
          <p className="text-sm text-slate-500 mt-1">{category.description}</p>
        </div>
      </div>

      {op.interest_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {op.interest_tags.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full font-medium"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-semibold text-slate-400 uppercase mb-2">OCEAN Profile</p>
          <OceanBars data={oceanData} />
        </div>
        <div>
          <OceanRadar {...oceanData} height={160} />
        </div>
      </div>

      {(op.search_keywords.length > 0 || op.hashtags.length > 0) && (
        <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-3">
          {op.search_keywords.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1.5">Keywords</p>
              <div className="flex flex-wrap gap-1">
                {op.search_keywords.slice(0, 5).map((kw) => (
                  <span key={kw} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}
          {op.hashtags.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1.5">Hashtags</p>
              <div className="flex flex-wrap gap-1">
                {op.hashtags.slice(0, 5).map((h) => (
                  <span key={h} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                    #{h}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
