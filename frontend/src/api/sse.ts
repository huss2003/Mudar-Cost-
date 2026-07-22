import client from './client';

/**
 * Polls /drawings/{id}/status until the drawing is `processed` or `error`.
 * Returns an AbortController-backed cancel handle so callers can stop polling
 * on unmount / project switch.
 */
export interface PollOpts {
  attempts?: number;
  intervalMs?: number;
  backoff?: boolean;
  onTick?: (status: string, attempts: number) => void;
}
export type PollStatus = 'processed' | 'detected' | 'error' | 'timeout';
export async function pollDrawingUntilReady(
  drawingId: number,
  opts: PollOpts = {},
): Promise<{ status: PollStatus; attempts: number; cancel: () => void }> {
  const { attempts = 30, intervalMs = 1500, backoff = true, onTick } = opts;
  const ctrl = new AbortController();
  let tried = 0;
  let delay = intervalMs;
  while (tried < attempts) {
    if (ctrl.signal.aborted) return { status: 'timeout', attempts: tried, cancel: () => {} };
    onTick?.('checking', tried);
    try {
      const r = await client.get(`/drawings/${drawingId}/status`);
      const status = r.data?.status as string | undefined;
      onTick?.(status ?? 'unknown', tried);
      if (status === 'processed' || status === 'detected' || status === 'error') {
        return { status, attempts: tried, cancel: ctrl.abort.bind(ctrl) };
      }
    } catch { /* swallow, retry */ }
    tried++;
    await new Promise<void>((res) => setTimeout(res, delay));
    if (backoff) delay = Math.min(delay * 1.5, 12_000);
  }
  return { status: 'timeout', attempts: tried, cancel: ctrl.abort.bind(ctrl) };
}

/**
 * Subscribes to /projects/{id}/live. Returns a disconnect handle.
 * The store and any other caller can swap it without knowing the URL shape.
 */
export interface LiveHandlers {
  onConnected?: () => void;
  onMaterialChanged?: (payload: { boq_item_id: number; total?: number; rate?: number; material_name?: string }) => void;
  onError?: () => void;
}
export function connectProjectLive(projectId: number, handlers: LiveHandlers): { close: () => void } {
  const url = `/api/v1/projects/${projectId}/live`;
  const es = new EventSource(url);
  es.addEventListener('connected', () => handlers.onConnected?.());
  es.addEventListener('material_changed', (event) => {
    try { handlers.onMaterialChanged?.(JSON.parse((event as MessageEvent).data)); } catch { /* swallow */ }
  });
  es.onerror = () => handlers.onError?.();
  return { close: () => es.close() };
}
