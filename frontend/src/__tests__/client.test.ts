/**
 * Vitest tests for the API client (client.ts):
 * - Auth interceptor injects token from store
 * - 401 response triggers token refresh or logout
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Request interceptor: injects auth token ───────────────────────────

describe('client request interceptor', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();

    // Import the actual auth store
    // We'll control the store state directly
  });

  it('should inject Bearer token from auth store', async () => {
    // Set up auth store with a token
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().login('test-token-123', 'refresh-xyz', {
      sub: 'user1', email: 'u@t.com', name: 'User', roles: [],
    });

    // Now import client (it reads from store on creation)
    const { default: client } = await import('../api/client');

    // Manually trigger the request interceptor
    const config: any = { headers: {} };
    const interceptedConfig = await client.interceptors.request.handlers[0].fulfilled(config);

    expect(interceptedConfig.headers.Authorization).toBe('Bearer test-token-123');
  });

  it('should not inject token when not authenticated', async () => {
    // No token in store
    const { default: client } = await import('../api/client');

    const config: any = { headers: {} };
    const interceptedConfig = await client.interceptors.request.handlers[0].fulfilled(config);

    expect(interceptedConfig.headers.Authorization).toBeUndefined();
  });

  it('should handle request interceptor error rejection', async () => {
    const { default: client } = await import('../api/client');

    const error = new Error('network error');
    await expect(
      client.interceptors.request.handlers[0].rejected(error),
    ).rejects.toThrow('network error');
  });
});

// ── Response interceptor: 401 handling ────────────────────────────────

describe('client response interceptor', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it('should pass through successful responses', async () => {
    const { default: client } = await import('../api/client');
    const response = { data: { ok: true }, status: 200 };

    const result = await client.interceptors.response.handlers[0].fulfilled(response);
    expect(result).toBe(response);
  });

  it('should trigger logout on 401 for auth endpoints', async () => {
    // Need to set up auth store and login first
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().login('token', 'refresh', {
      sub: 'u', email: 'u@t.com', name: 'U', roles: [],
    });

    const { default: client } = await import('../api/client');
    const axiosError = createAxiosError(401, '/api/v1/auth/refresh');

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    // Should be logged out
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('should retry original request after successful token refresh', async () => {
    const { useAuthStore } = await import('../store/auth');
    // Set up initial auth
    useAuthStore.getState().login('old-token', 'old-refresh', {
      sub: 'u', email: 'u@t.com', name: 'U', roles: [],
    });

    // Mock the refreshAccessToken to succeed
    vi.spyOn(useAuthStore.getState(), 'refreshAccessToken').mockImplementation(async () => {
      useAuthStore.getState().setTokens('new-token', 'new-refresh');
    });

    const { default: client } = await import('../api/client');
    const axiosError = createAxiosError(401, '/api/v1/boq-items');

    // The interceptor should try to refresh and retry
    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    // Token should have been refreshed
    expect(useAuthStore.getState().token).toBe('new-token');
  });

  it('should logout when refresh fails', async () => {
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().login('token', 'refresh', {
      sub: 'u', email: 'u@t.com', name: 'U', roles: [],
    });

    // Mock refreshAccessToken to reject
    vi.spyOn(useAuthStore.getState(), 'refreshAccessToken').mockImplementation(async () => {
      throw new Error('refresh failed');
    });

    const { default: client } = await import('../api/client');
    const axiosError = createAxiosError(401, '/api/v1/boq-items');

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('should pass through non-401 errors', async () => {
    const { default: client } = await import('../api/client');
    const axiosError = createAxiosError(403, '/api/v1/boq-items');

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();
  });

  it('should queue concurrent 401 requests during refresh', async () => {
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().login('token', 'refresh', {
      sub: 'u', email: 'u@t.com', name: 'U', roles: [],
    });

    let refreshCount = 0;
    vi.spyOn(useAuthStore.getState(), 'refreshAccessToken').mockImplementation(async () => {
      refreshCount++;
      useAuthStore.getState().setTokens('new-token', 'new-refresh');
    });

    const { default: client } = await import('../api/client');

    // Create two 401 errors to simulate concurrent requests
    const err1 = createAxiosError(401, '/api/v1/boq-items');
    const err2 = createAxiosError(401, '/api/v1/materials');

    await Promise.allSettled([
      client.interceptors.response.handlers[0].rejected(err1),
      client.interceptors.response.handlers[0].rejected(err2),
    ]);

    // Should have only refreshed once (the queue mechanism)
    expect(refreshCount).toBe(1);
  });
});

// ── logout function ───────────────────────────────────────────────────

describe('logout function', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it('should clear auth state on logout', async () => {
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().login('token', 'refresh', {
      sub: 'u', email: 'u@t.com', name: 'U', roles: [],
    });

    // Mock client.post to succeed
    const { default: client } = await import('../api/client');
    vi.spyOn(client, 'post').mockResolvedValue({ data: {} });

    const { logout } = await import('../api/client');
    await logout();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
  });
});

// ── Helper ────────────────────────────────────────────────────────────

function createAxiosError(status: number, url: string): any {
  const error: any = new Error(`Request failed with status code ${status}`);
  error.isAxiosError = true;
  error.response = {
    status,
    data: {},
    headers: {},
    statusText: 'Error',
  };
  error.config = {
    url,
    headers: {},
    _retry: false,
  };
  return error;
}
