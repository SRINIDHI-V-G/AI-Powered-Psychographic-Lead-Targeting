import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { LeadTier } from './types/api';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getTier(score: number): LeadTier {
  if (score >= 75) return 'Hot';
  if (score >= 50) return 'Warm';
  return 'Cold';
}

export function formatScore(score: number): string {
  return (score / 10).toFixed(1);
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelative(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function getPipelineLabel(step: number): string {
  const labels: Record<number, string> = {
    0: 'Pending',
    1: 'Generating Motivations',
    2: 'Motivations Ready',
    3: 'Discovering Users',
    4: 'Collecting Content',
    5: 'NLP Processing',
    6: 'OCEAN Scoring',
    7: 'Matching',
    8: 'Ranking',
    9: 'Complete',
  };
  return labels[step] ?? 'Unknown';
}

export function isRunning(status: string): boolean {
  return [
    'processing',
    'discovering',
    'nlp_processing',
    'ocean_scoring',
    'matching',
    'ranking',
  ].includes(status);
}

export function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((n) => n[0]?.toUpperCase() ?? '')
    .join('');
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
