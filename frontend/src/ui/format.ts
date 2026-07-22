/**
 * Shared formatting helpers used across the UI.
 */

export const formatINR = (n: number, opts: { round?: boolean } = {}): string =>
  (opts.round ? Math.round(n) : n).toLocaleString('en-IN');

export const pad3 = (n: number | string | null | undefined): string =>
  String(n ?? '').padStart(3, '0');

export const fmtDate = (d: string | Date): string =>
  new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });

export const fmtDateTime = (d: string | Date): string =>
  new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
