/**
 * Provider color palette — fully dynamic.
 *
 * Known providers get a stable brand color.
 * Unknown/future providers get a deterministic color from a palette
 * based on a simple string hash, so no frontend code changes are
 * needed when a new provider is added to the backend.
 */

const KNOWN: Record<string, string> = {
  reddit:         '#ff4500',
  instagram:      '#e1306c',
  youtube:        '#ff0000',
  twitter:        '#1da1f2',
  'twitter/x':    '#1da1f2',
  linkedin:       '#0077b5',
  'google reviews': '#fbbc04',
  amazon:         '#ff9900',
  tiktok:         '#010101',
  mock:           '#94a3b8',
};

// Fallback palette for unknown providers
const PALETTE = [
  '#6366f1', '#0891b2', '#059669', '#d97706',
  '#7c3aed', '#db2777', '#dc2626', '#0d9488',
];

function hashString(s: string): number {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) & 0x7fffffff;
  return h;
}

export function getProviderColor(provider: string): string {
  const key = provider.toLowerCase().trim();
  return KNOWN[key] ?? PALETTE[hashString(key) % PALETTE.length];
}
