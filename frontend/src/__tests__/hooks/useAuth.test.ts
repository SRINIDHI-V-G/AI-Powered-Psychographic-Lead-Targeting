import { getApiKey, setApiKey, removeApiKey, isAuthenticated, setDemoMode, isDemoMode } from '@/lib/auth';

describe('auth module', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns null when no key is stored', () => {
    expect(getApiKey()).toBeNull();
  });

  it('stores and retrieves API key', () => {
    setApiKey('test-key-123');
    expect(getApiKey()).toBe('test-key-123');
  });

  it('isAuthenticated returns false when no key', () => {
    expect(isAuthenticated()).toBe(false);
  });

  it('isAuthenticated returns true after setApiKey', () => {
    setApiKey('my-api-key');
    expect(isAuthenticated()).toBe(true);
  });

  it('removeApiKey clears the stored key', () => {
    setApiKey('to-be-removed');
    removeApiKey();
    expect(getApiKey()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });

  it('setDemoMode stores product id', () => {
    setDemoMode('product-abc');
    expect(isDemoMode()).toBe(true);
  });

  it('removeApiKey also clears demo mode', () => {
    setApiKey('key');
    setDemoMode('product-123');
    removeApiKey();
    expect(isDemoMode()).toBe(false);
  });
});
