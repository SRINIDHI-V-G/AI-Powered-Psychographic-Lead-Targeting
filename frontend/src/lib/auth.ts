const STORAGE_KEY = 'psycholead_api_key';
const DEMO_KEY = 'psycholead_demo_mode';

export function getApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEY);
}

export function setApiKey(key: string): void {
  localStorage.setItem(STORAGE_KEY, key);
}

export function removeApiKey(): void {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(DEMO_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getApiKey());
}

export function setDemoMode(productId: string): void {
  localStorage.setItem(DEMO_KEY, productId);
}

export function getDemoProductId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(DEMO_KEY);
}

export function isDemoMode(): boolean {
  return Boolean(getDemoProductId());
}
