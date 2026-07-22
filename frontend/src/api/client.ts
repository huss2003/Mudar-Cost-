import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

const client = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Response Interceptor ─────────────────────────────────────────────────
//  1. Normalises the structured error envelope (trace_id, code, message)
//     into a consistent error message for the UI.
//  2. Retries GET requests up to 2 times on 5xx (server errors) with
//     exponential backoff.
// ─────────────────────────────────────────────────────────────────────────

// Track retry attempts per request to avoid infinite loops
interface RetryConfig extends InternalAxiosRequestConfig {
  _retryCount?: number;
  _retry?: boolean;
}

const MAX_RETRIES = 2;

function getRetryDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 5000); // 1s, 2s, cap at 5s
}

function shouldRetry(error: AxiosError, config: RetryConfig): boolean {
  const status = error.response?.status ?? 0;
  const method = (config.method ?? 'get').toLowerCase();
  // Only retry GET/HEAD/OPTIONS on 5xx (server errors)
  return (
    method === 'get' &&
    status >= 500 &&
    status < 600 &&
    (config._retryCount ?? 0) < MAX_RETRIES
  );
}

client.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryConfig | undefined;
    if (!originalRequest) return Promise.reject(error);

    // ── Structured error envelope parsing ─────────────────────────────
    const responseData = error.response?.data as
      | { error?: { message?: string; code?: string; trace_id?: string; hint?: string } }
      | undefined;
    const structuredMsg = responseData?.error?.message;
    const structuredCode = responseData?.error?.code;
    const structuredHint = responseData?.error?.hint;
    const structuredTraceId = responseData?.error?.trace_id;

    // Attach parsed metadata to the error for consumers
    if (structuredMsg || structuredCode) {
      (error as any)._structured = {
        message: structuredMsg ?? error.message,
        code: structuredCode ?? 'UNKNOWN',
        hint: structuredHint,
        traceId: structuredTraceId,
      };
    }

    // ── Retry GET requests on 5xx with exponential backoff ────────────
    if (shouldRetry(error, originalRequest)) {
      originalRequest._retryCount = (originalRequest._retryCount ?? 0) + 1;
      const delay = getRetryDelay(originalRequest._retryCount);
      console.warn(
        `[API Retry] ${originalRequest.method?.toUpperCase()} ${originalRequest.url} ` +
          `failed (${error.response?.status}), retry ${originalRequest._retryCount}/${MAX_RETRIES} after ${delay}ms`,
      );
      await new Promise((resolve) => setTimeout(resolve, delay));
      return client(originalRequest);
    }

    return Promise.reject(error);
  },
);

export default client;
