/**
 * Vitest tests for the API client (client.ts):
 * - Response error envelope parsing
 * - 5xx retry logic
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Response interceptor ───────────────────────────────────────────────

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

  it('should pass through non-5xx errors', async () => {
    const { default: client } = await import('../api/client');
    const axiosError = createAxiosError(403, '/api/v1/boq-items');

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();
  });

  it('should parse structured error envelope', async () => {
    const { default: client } = await import('../api/client');

    const error: any = createAxiosError(422, '/api/v1/boq-items');
    error.response.data = {
      error: {
        message: 'Validation failed',
        code: 'VALIDATION_ERROR',
        trace_id: 'abc-123',
        hint: 'Check input fields',
      },
    };

    await expect(
      client.interceptors.response.handlers[0].rejected(error),
    ).rejects.toMatchObject({
      _structured: {
        message: 'Validation failed',
        code: 'VALIDATION_ERROR',
        hint: 'Check input fields',
        traceId: 'abc-123',
      },
    });
  });
});

// ── 5xx Retry Logic ────────────────────────────────────────────────────

describe('client 5xx retry logic', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it('should retry GET requests on 5xx', async () => {
    const { default: client } = await import('../api/client');

    // Create an error with retry tracking
    const axiosError = createAxiosError(503, '/api/v1/boq-items');
    axiosError.config.method = 'get';

    // Should retry (which will fail again) then reject
    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    // After retries the _retryCount should be 1 or more
    expect(axiosError.config._retryCount).toBeGreaterThanOrEqual(1);
  });

  it('should not retry non-GET methods on 5xx', async () => {
    const { default: client } = await import('../api/client');

    const axiosError = createAxiosError(503, '/api/v1/boq-items');
    axiosError.config.method = 'post';

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    // Should NOT have retry count incremented
    expect(axiosError.config._retryCount).toBeUndefined();
  });

  it('should not retry on 4xx errors', async () => {
    const { default: client } = await import('../api/client');

    const axiosError = createAxiosError(400, '/api/v1/boq-items');
    axiosError.config.method = 'get';

    await expect(
      client.interceptors.response.handlers[0].rejected(axiosError),
    ).rejects.toThrow();

    expect(axiosError.config._retryCount).toBeUndefined();
  });

  it('should handle response interceptor error rejection', async () => {
    const { default: client } = await import('../api/client');

    const error = createAxiosError(500, '/api/v1/boq-items');
    await expect(
      client.interceptors.response.handlers[0].rejected(error),
    ).rejects.toThrow();
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
