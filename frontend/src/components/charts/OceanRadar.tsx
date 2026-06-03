'use client';

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

interface OceanRadarProps {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
  height?: number;
  color?: string;
}

export function OceanRadar({
  openness,
  conscientiousness,
  extraversion,
  agreeableness,
  neuroticism,
  height = 200,
  color = '#6366f1',
}: OceanRadarProps) {
  const chartData = [
    { dimension: 'O', value: openness / 10 },
    { dimension: 'C', value: conscientiousness / 10 },
    { dimension: 'E', value: extraversion / 10 },
    { dimension: 'A', value: agreeableness / 10 },
    { dimension: 'N', value: neuroticism / 10 },
  ];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12, fill: '#475569' }} />
        <Radar
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.25}
          strokeWidth={2}
        />
        <Tooltip formatter={(v: number) => [v.toFixed(1), 'Score']} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
