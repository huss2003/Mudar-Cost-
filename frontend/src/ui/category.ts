export type ObjectCategory =
  | 'wall' | 'partition' | 'door' | 'window' | 'furniture' | 'electrical' | 'text' | 'other';

/** Bucket an `object_type` (free-form) into a closed taxonomy. */
export function categorizeObjectType(type: string | null | undefined): ObjectCategory {
  const t = (type ?? '').toLowerCase();
  if (t.includes('partition') || t.includes('interior')) return 'partition';
  if (t.includes('door')) return 'door';
  if (t.includes('window')) return 'window';
  if (t.includes('furniture') || t.includes('chair') || t.includes('table')) return 'furniture';
  if (t.includes('electric') || t.includes('symbol') || t.includes('point')) return 'electrical';
  if (t.includes('text') || t.includes('label')) return 'text';
  if (t.includes('wall') || t.includes('exterior')) return 'wall';
  return 'other';
}

export interface RenderedObjectStyle {
  cls: string;
  fill: string;
  stroke: string;
  strokeWidth: number;
  strokeDashArray?: string;
  /** Default 3D height (metres). */
  height3d: number;
  /** 3D colour. */
  tone: string;
}

export const OBJECT_STYLE: Record<ObjectCategory, RenderedObjectStyle> = {
  wall:       { cls: 'obj-wall',       fill: 'var(--ink)',                       stroke: 'var(--ink)',                strokeWidth: 3, height3d: 2.6, tone: '#1A1815' },
  partition:  { cls: 'obj-partition',  fill: 'rgba(27,77,126,0.06)',              stroke: 'var(--draft)',              strokeWidth: 1.25, strokeDashArray: '6,4', height3d: 2.5, tone: '#1B4D7E' },
  door:       { cls: 'obj-door',       fill: 'none',                              stroke: 'var(--warm)',               strokeWidth: 1.25, height3d: 2.1, tone: '#B8501F' },
  window:     { cls: 'obj-window',     fill: 'rgba(27,77,126,0.4)',               stroke: 'var(--draft)',              strokeWidth: 2,   height3d: 1.2, tone: '#8AB6D6' },
  furniture:  { cls: 'obj-furniture',  fill: 'var(--paper-2)',                    stroke: 'var(--ink-2)',              strokeWidth: 1.25, height3d: 0.7, tone: '#5A574E' },
  electrical: { cls: 'obj-electrical', fill: 'var(--accent)',                     stroke: 'var(--ink)',                strokeWidth: 1,   height3d: 0.2, tone: '#C7F23A' },
  text:       { cls: 'obj-text',       fill: 'none',                              stroke: 'var(--ink)',                strokeWidth: 0,   height3d: 0.2, tone: '#1A1815' },
  other:      { cls: 'obj-wall',       fill: 'none',                              stroke: 'rgba(26,24,21,0.4)',         strokeWidth: 1,   strokeDashArray: '4,2', height3d: 0.7, tone: '#888888' },
};

export function styleFor(type: string | null | undefined): RenderedObjectStyle {
  return OBJECT_STYLE[categorizeObjectType(type)];
}
