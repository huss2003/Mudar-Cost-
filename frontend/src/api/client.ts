import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

const baseURL = (import.meta.env.VITE_API_BASE as string | undefined) || '/api/v1';

const client = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: false,
});

interface RetryConfig extends InternalAxiosRequestConfig {
  _retryCount?: number;
}

const MAX_RETRIES = 2;

function getRetryDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 5000);
}

function shouldRetry(error: AxiosError, config: RetryConfig): boolean {
  const status = error.response?.status ?? 0;
  const method = (config.method ?? 'get').toLowerCase();
  return (
    method === 'get' &&
    status >= 500 &&
    status < 600 &&
    (config._retryCount ?? 0) < MAX_RETRIES
  );
}

client.interceptors.response.use(
  (response: AxiosResponse) => {
    const body = response.data;
    if (
      body && typeof body === 'object' && !Array.isArray(body) &&
      Object.prototype.hasOwnProperty.call(body, 'success') &&
      (body as any).success === true &&
      Object.prototype.hasOwnProperty.call(body, 'data')
    ) {
      response.data = (body as any).data;
    } else if (
      body && typeof body === 'object' && !Array.isArray(body) &&
      Object.prototype.hasOwnProperty.call(body, 'success') &&
      (body as any).success === false &&
      Object.prototype.hasOwnProperty.call(body, 'error')
    ) {
      const env = (body as any).error ?? {};
      return Promise.reject(
        Object.assign(new Error(env.message ?? 'API error'), {
          isAxiosError: true,
          response,
          code: env.code ?? 'UNKNOWN',
          traceId: env.trace_id,
        }),
      );
    }
    return response;
  },
  async (error: AxiosError) => {
    const cfg = error.config as RetryConfig | undefined;
    if (!cfg) return Promise.reject(error);

    const body = error.response?.data as { error?: { message?: string; code?: string; trace_id?: string; hint?: string } } | undefined;
    const env = body?.error;
    if (env?.message || env?.code) {
      (error as any)._structured = {
        message: env.message ?? error.message,
        code: env.code ?? 'UNKNOWN',
        hint: env.hint,
        traceId: env.trace_id,
      };
    }

    if (shouldRetry(error, cfg)) {
      cfg._retryCount = (cfg._retryCount ?? 0) + 1;
      await new Promise((r) => setTimeout(r, getRetryDelay(cfg._retryCount!)));
      return client(cfg);
    }
    return Promise.reject(error);
  },
);

export default client;
