import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useProjectStore } from '../store';
import { fetchDrawings, fetchDrawingObjects, uploadDrawing } from '../api/drawings';
import { computeQuantities } from '../api/boq';
import { pollDrawingUntilReady } from '../api/sse';
import { OBJECT_STYLE, categorizeObjectType } from '../ui/category';
import { FINISH_PRESET_LIST } from '../types';
import type { Drawing, DetectedObject } from '../types';

const ACCEPT = '.dwg,.dxf,.pdf,.png,.jpg,.jpeg';

export default function PlanView() {
  const project = useProjectStore((s) => s.currentProject);
  const drawingId = useProjectStore((s) => s.drawingId);
  const setDrawingId = useProjectStore((s) => s.setDrawingId);
  const objects = useProjectStore((s) => s.detectedObjects);
  const setObjects = useProjectStore((s) => s.setDetectedObjects);
  const selectedId = useProjectStore((s) => s.selectedObjectId);
  const selectObject = useProjectStore((s) => s.selectObject);
  const view = useProjectStore((s) => s.viewMode);
  const setViewMode = useProjectStore((s) => s.setViewMode);
  const finishPreset = useProjectStore((s) => s.finishPreset);
  const setFinishPreset = useProjectStore((s) => s.setFinishPreset);

  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [phase, setPhase] = useState<'idle' | 'computing'>('idle');
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!project) return;
    fetchDrawings(project.id)
      .then((d) => { setDrawings(d); if (!drawingId && d.length > 0) setDrawingId(d[0].id); })
      .catch(() => setDrawings([]));
  }, [project, drawingId, setDrawingId]);

  useEffect(() => {
    if (!drawingId) { setObjects([]); return; }
    const ctrl = new AbortController();
    pollDrawingUntilReady(drawingId, { attempts: 30, onTick: () => undefined }).then(async () => {
      if (ctrl.signal.aborted) return;
      try {
        const objs = await fetchDrawingObjects(drawingId);
        if (!ctrl.signal.aborted) setObjects(objs);
      } catch { /* ignore */ }
    });
    return () => ctrl.abort();
  }, [drawingId, setObjects]);

  async function onFile(file: File) {
    if (!project) return;
    try {
      const res = await uploadDrawing(file, project.id);
      setDrawingId(res.drawing_id);
      setDrawings(await fetchDrawings(project.id));
    } catch (e: any) {
      alert(`Upload failed: ${e?.message ?? e}`);
    }
  }

  async function compute() {
    if (!project) return;
    setPhase('computing');
    try { await computeQuantities(project.id); }
    catch (e: any) { alert(`Compute failed: ${e?.message ?? e}`); }
    finally { setPhase('idle'); }
  }

  const is2D = view === 'plan' || view === 'quantities' || view === 'materials';

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: view === 'plan' ? '240px 1fr' : '1fr',
      height: '100%',
      background: 'var(--paper)',
    }}>
      <aside style={{
        borderRight: '1px solid var(--rule-strong)',
        padding: '20px',
        overflow: 'auto',
        background: 'var(--paper)',
      }}>
        <div className="kicker" style={{ marginBottom: 12 }}>Drawings · this project</div>
        <button className="btn btn-secondary" style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
          onClick={() => fileInput.current?.click()} type="button">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square"/>
          </svg>
          Add drawing
        </button>
        <input ref={fileInput} type="file" accept={ACCEPT} hidden
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />

        <hr className="hr" style={{ margin: '20px 0' }} />

        {drawings.length === 0 ? (
          <div style={{ padding: '20px 0', color: 'var(--ink-3)', fontSize: 13 }}>
            <div className="kicker" style={{ marginBottom: 6 }}>Empty</div>
            Add a floor plan to begin detection.
          </div>
        ) : (
          <div>{drawings.map((d) => <DrawingRow key={d.id} d={d} active={d.id === drawingId} onClick={() => setDrawingId(d.id)} />)}</div>
        )}

        <hr className="hr" style={{ margin: '24px 0' }} />

        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '14px' }}
          onClick={compute} disabled={!drawingId || phase === 'computing'} type="button">
          {phase === 'computing' ? (
            <><svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ animation: 'spin 1s linear infinite' }}>
              <circle cx="7" cy="7" r="5" stroke="var(--accent-ink)" strokeWidth="1.5" fill="none" strokeDasharray="20" /></svg>processing…</>
          ) : (
            <><svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7 L7 2 L12 7 L7 12 Z" stroke="var(--accent-ink)" strokeWidth="1.5" fill="none"/></svg>
              Compute quantities<span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.6 }}>↵</span></>
          )}
        </button>
      </aside>

      <div style={{ position: 'relative', overflow: 'hidden' }}>
        <CanvasToolbar is2D={is2D} onViewChange={setViewMode} preset={finishPreset} onPresetChange={setFinishPreset} />

        <div className="canvas-grid" style={{ position: 'absolute', top: 56, left: 0, right: 0, bottom: 0 }}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f); }}
        >
          {is2D
            ? <Plan2D objects={objects} selectedId={selectedId} onSelect={selectObject}
                drawingUrl={drawings.find(d => d.id === drawingId)?.file_path ?? null} />
            : <Plan3D objects={objects} onSelect={selectObject} />}

          {drag && (
            <div style={{
              position: 'absolute', inset: 0,
              border: '3px dashed var(--accent)', background: 'var(--accent)',
              color: 'var(--accent-ink)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--font-display)', fontSize: 40, fontStyle: 'italic', opacity: 0.9,
            }}>release to upload</div>
          )}
        </div>

        {drawingId && (
          <div style={{
            position: 'absolute', top: 12, right: 12,
            display: 'flex', gap: 8, alignItems: 'center',
            background: 'var(--paper)', border: '1px solid var(--rule-strong)',
            padding: '6px 10px', borderRadius: 'var(--r-md)',
          }}>
            <span className={`dot ${objects.length === 0 ? 'dot-pending' : 'dot-active'}`} />
            <span className="num" style={{ fontSize: 11 }}>{objects.length}</span>
            <span style={{ fontSize: 11, fontWeight: 500 }}>objects</span>
          </div>
        )}
      </div>
    </div>
  );
}

function CanvasToolbar({ is2D, onViewChange, preset, onPresetChange }:
  { is2D: boolean; onViewChange: (v: any) => void; preset: string; onPresetChange: (p: any) => void }) {
  return (
    <div style={{
      position: 'absolute', top: 12, left: 12, right: 12, zIndex: 10,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', pointerEvents: 'none',
    }}>
      <div className="togglegroup" style={{ pointerEvents: 'auto' }}>
        <button data-active={is2D} onClick={() => onViewChange('plan')}>2D plan</button>
        <button data-active={!is2D} onClick={() => onViewChange('costs')}>3D view</button>
      </div>
      <div className="togglegroup" style={{ pointerEvents: 'auto' }}>
        {FINISH_PRESET_LIST.map((p) => (
          <button key={p} data-active={preset === p} onClick={() => onPresetChange(p)}>
            {p.charAt(0).toUpperCase() + p.slice(1)}
          </button>
        ))}
      </div>
    </div>
  );
}

function DrawingRow({ d, active, onClick }: { d: Drawing; active: boolean; onClick: () => void }) {
  const status = d.status;
  return (
    <button type="button" onClick={onClick} style={{
      display: 'block', width: '100%',
      padding: '10px 12px',
      marginBottom: 6,
      background: active ? 'var(--accent)' : 'transparent',
      color: active ? 'var(--accent-ink)' : 'var(--ink)',
      border: '1px solid',
      borderColor: active ? 'var(--ink)' : 'var(--rule-strong)',
      boxShadow: active ? '2px 2px 0 0 var(--ink)' : 'none',
      cursor: 'pointer',
      textAlign: 'left',
      fontFamily: 'inherit',
      fontSize: 12,
      transition: 'all var(--t-fast) var(--ease)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
        <span className={`dot ${(status === 'processed' || status === 'detected') ? 'dot-active' : status === 'error' ? 'dot-error' : 'dot-pending'}`} />
      </div>
      <div className="kicker" style={{ marginTop: 2, color: active ? 'var(--accent-ink)' : 'var(--ink-3)', textTransform: 'capitalize' }}>
        {status} · {new Date(d.created_at).toLocaleDateString()}
      </div>
    </button>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Plan2D — 2-D viewer with demo floor plan fallback
   ───────────────────────────────────────────────────────────────────────── */

function Plan2D({ objects, selectedId, onSelect, drawingUrl }:
  { objects: DetectedObject[]; selectedId: number | null; onSelect: (id: number | null) => void; drawingUrl: string | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = containerRef.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* Convert normalised 0-1 bbox coordinates to mm scale (15 m × 10 m office) */
  const scaledObjects = useMemo(() =>
    objects.map((o) => ({
      ...o,
      bbox_x: o.bbox_x * 15000,
      bbox_y: o.bbox_y * 10000,
      length: o.length * 15000,
      width:  o.width  * 10000,
    })),
  [objects]);

  const projection = useMemo(() => {
    if (scaledObjects.length === 0 || size.w === 0 || size.h === 0) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const o of scaledObjects) {
      minX = Math.min(minX, o.bbox_x);
      minY = Math.min(minY, o.bbox_y);
      maxX = Math.max(maxX, o.bbox_x + o.length);
      maxY = Math.max(maxY, o.bbox_y + o.width);
    }
    const pad = 40;
    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);
    const scale = Math.min((size.w - pad * 2) / w, (size.h - pad * 2) / h);
    const ox = (size.w - w * scale) / 2 - minX * scale;
    const oy = (size.h - h * scale) / 2 - minY * scale;
    return { scale, ox, oy };
  }, [scaledObjects, size]);

  /* ── Demo floor-plan when no real objects exist ──────────────────────── */
  if (!scaledObjects.length || !projection) {
    return <DemoFloorPlan containerRef={containerRef} onSelect={onSelect} />;
  }

  const legend = [
    { cls: 'wall',       stroke: 'var(--ink)',  shape: { w: 12, h: 4, type: 'rect' as const } },
    { cls: 'partition',  stroke: 'var(--draft)', shape: { w: 12, h: 4, type: 'dash' as const } },
    { cls: 'door',       stroke: 'var(--warm)',  shape: { w: 12, h: 4, type: 'rect' as const } },
    { cls: 'window',     stroke: 'var(--draft)', shape: { w: 12, h: 4, type: 'rect' as const } },
    { cls: 'furniture',  stroke: 'var(--ink-2)', shape: { w: 12, h: 4, type: 'rect' as const } },
    { cls: 'electrical', stroke: 'var(--ink)',  shape: { w: 12, h: 4, type: 'accent' as const } },
  ];

  return (
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
      <svg width={size.w} height={size.h} style={{ display: 'block' }}
        onClick={(e) => { if (e.target === e.currentTarget) onSelect(null); }}>
        <defs>
          <pattern id="dot5" x="0" y="0" width="48" height="48" patternUnits="userSpaceOnUse">
            <circle cx="0.5" cy="0.5" r="0.5" fill="var(--rule-strong)" />
          </pattern>
          <marker id="dim" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M0 0 L10 10 M10 0 L0 10" stroke="var(--ink-3)" strokeWidth="0.8"/>
          </marker>
        </defs>
        <rect width={size.w} height={size.h} fill="url(#dot5)" opacity={0.4} />

        {/* Floor plan background image */}
        {drawingUrl && (
          <image
            href={`https://pecnshwflkwpnwiskgmg.supabase.co/storage/v1/object/public/drawings/${drawingUrl}`}
            x={projection.ox} y={projection.oy}
            width={15000 * projection.scale} height={10000 * projection.scale}
            preserveAspectRatio="xMidYMid meet" opacity={0.35}
          />
        )}

        <g transform={`translate(${projection.ox} ${projection.oy}) scale(${projection.scale})`}>
          {scaledObjects.map((o) => {
            const cat = categorizeObjectType(o.object_type);
            const s = OBJECT_STYLE[cat];
            const sel = o.id === selectedId;
            const strokeWidth = sel ? 2.5 : s.strokeWidth;
            const fill = sel ? 'var(--accent)' : s.fill;
            const stroke = sel ? 'var(--ink)' : s.stroke;
            return (
              <g key={o.id} style={{ cursor: 'pointer' }} onClick={(e) => { e.stopPropagation(); onSelect(o.id); }}>
                <rect
                  x={o.bbox_x} y={o.bbox_y}
                  width={Math.max(o.length * projection.scale, 3)}
                  height={Math.max(o.width * projection.scale, 3)}
                  fill={fill} stroke={stroke} strokeWidth={strokeWidth}
                  strokeDasharray={sel ? undefined : s.strokeDashArray}
                  rx={1}
                />
                {o.label && o.width * projection.scale > 24 && o.length * projection.scale > 36 && (
                  <text x={o.bbox_x + 8} y={o.bbox_y + 18}
                    fontFamily="var(--font-body)" fontSize={11}
                    fill={sel ? 'var(--accent-ink)' : 'var(--ink-2)'}
                    style={{ pointerEvents: 'none' }}>
                    {o.label}
                  </text>
                )}
                {sel && (
                  <>
                    <rect x={o.bbox_x - 4} y={o.bbox_y - 4}
                      width={Math.max(o.length * projection.scale, 3) + 8}
                      height={Math.max(o.width * projection.scale, 3) + 8}
                      fill="none" stroke="var(--accent)" strokeWidth={1} strokeDasharray="3,2" pointerEvents="none" />
                    <g pointerEvents="none">
                      <line x1={o.bbox_x} y1={o.bbox_y - 10}
                        x2={o.bbox_x + o.length * projection.scale} y2={o.bbox_y - 10}
                        stroke="var(--ink-3)" strokeWidth={0.5} markerStart="url(#dim)" markerEnd="url(#dim)" />
                      <text x={o.bbox_x + (o.length * projection.scale) / 2} y={o.bbox_y - 14}
                        textAnchor="middle" fontFamily="var(--font-mono)" fontSize={10} fill="var(--ink-3)">
                        {Math.round(o.length)} mm
                      </text>
                    </g>
                  </>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div style={{
        position: 'absolute', left: 12, bottom: 12,
        background: 'var(--paper)', border: '1px solid var(--rule-strong)',
        padding: '12px 14px', fontSize: 11,
      }}>
        <div className="kicker" style={{ marginBottom: 6 }}>Legend</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 10px' }}>
          {legend.map((l) => (
            <Row key={l.cls} shape={l.shape} stroke={l.stroke} label={l.cls.charAt(0).toUpperCase() + l.cls.slice(1)} />
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   DemoFloorPlan — SVG office layout shown when no real objects exist
   ───────────────────────────────────────────────────────────────────────── */

function DemoFloorPlan({ containerRef, onSelect }: {
  containerRef: React.RefObject<HTMLDivElement>;
  onSelect: (id: number | null) => void;
}) {
  const W = 15000, H = 10000;

  /* colour constants matching the legend */
  const wallC = '#1A1815';
  const partC = '#1B4D7E';
  const doorC = '#B8501F';
  const furnC = '#5A574E';
  const fills = ['rgba(237,234,225,0.12)', 'rgba(237,234,225,0.06)', 'rgba(200,220,240,0.08)', 'rgba(200,220,240,0.14)'];

  /* ── room definitions ──────────────────────────────────────────────── */
  const rooms = [
    { name: 'Reception',              x: 200,  y: 200,  w: 4800, h: 3800, lx: 2600, ly: 1600, fi: 0 },
    { name: 'Waiting Area',           x: 200,  y: 2400, w: 4800, h: 1600, lx: 2600, ly: 3300, fi: 1 },
    { name: 'Meeting Room\n10pax',    x: 5000, y: 200,  w: 4000, h: 3800, lx: 7000, ly: 1900, fi: 2 },
    { name: 'Meeting Room\n6pax',     x: 9000, y: 200,  w: 3200, h: 3800, lx: 10600,ly: 1900, fi: 3 },
    { name: 'Phone\nBooth 1',        x: 12200,y: 200,  w: 2600, h: 1900, lx: 13500,ly: 1050, fi: 0 },
    { name: 'Phone\nBooth 2',        x: 12200,y: 2100, w: 2600, h: 1900, lx: 13500,ly: 2950, fi: 1 },
    { name: 'Cabin-1',               x: 200,  y: 4000, w: 3300, h: 3000, lx: 1850, ly: 5500, fi: 2 },
    { name: 'Cabin-2',               x: 3500, y: 4000, w: 3000, h: 3000, lx: 5000, ly: 5500, fi: 3 },
    { name: 'Cabin-3',               x: 6500, y: 4000, w: 3000, h: 3000, lx: 8000, ly: 5500, fi: 0 },
    { name: 'Cabin-4',               x: 9500, y: 4000, w: 2700, h: 3000, lx: 10850,ly: 5500, fi: 1 },
    { name: 'Discussion\nBooth',     x: 12200,y: 4000, w: 2600, h: 3000, lx: 13500,ly: 5500, fi: 2 },
    { name: 'Workstations',          x: 200,  y: 7000, w: 6300, h: 3000, lx: 3350, ly: 8500, fi: 3 },
    { name: 'Pantry',                x: 6500, y: 7000, w: 3000, h: 1500, lx: 8000, ly: 7750, fi: 0 },
    { name: 'Cafeteria',             x: 9500, y: 7000, w: 2700, h: 1500, lx: 10850,ly: 7750, fi: 1 },
    { name: 'Server\nRoom',          x: 6500, y: 8500, w: 3000, h: 1500, lx: 8000, ly: 9300, fi: 2 },
    { name: 'Store\nRoom',           x: 9500, y: 8500, w: 2700, h: 1500, lx: 10850,ly: 9300, fi: 3 },
    { name: 'Ladies\nToilet',        x: 12200,y: 7000, w: 2600, h: 1500, lx: 13500,ly: 7750, fi: 0 },
    { name: 'Gents\nToilet',         x: 12200,y: 8500, w: 2600, h: 1500, lx: 13500,ly: 9300, fi: 1 },
  ];

  /* ── interior wall segments [x1, y1, x2, y2] ──────────────────────── */
  const walls: [number, number, number, number][] = [
    /* horizontal partitions */
    [200, 4000, 14800, 4000],
    [200, 7000, 14800, 7000],
    [6500, 8500, 14800, 8500],
    [12200, 2100, 14800, 2100],
    /* vertical partitions — row 1 */
    [5000, 200, 5000, 4000],
    [9000, 200, 9000, 4000],
    [12200, 200, 12200, 4000],
    /* vertical partitions — row 2 */
    [3500, 4000, 3500, 7000],
    [6500, 4000, 6500, 7000],
    [9500, 4000, 9500, 7000],
    [12200, 4000, 12200, 7000],
    /* vertical partitions — row 3 */
    [6500, 7000, 6500, 10000],
    [9500, 7000, 9500, 10000],
    [12200, 7000, 12200, 10000],
  ];

  /* ── door arcs (quarter-circle, r = 800 mm) ───────────────────────── */
  const doorPaths = [
    'M 2600 3200 A 800 800 0 0 1 3400 4000',
    'M 7000 3200 A 800 800 0 0 1 7800 4000',
    'M 10600 3200 A 800 800 0 0 1 11400 4000',
    'M 13500 3200 A 800 800 0 0 1 14300 4000',
    'M 4300 5400 A 800 800 0 0 1 3500 6200',
    'M 7300 5400 A 800 800 0 0 1 6500 6200',
    'M 10300 5400 A 800 800 0 0 1 9500 6200',
    'M 13000 5400 A 800 800 0 0 1 12200 6200',
    'M 3350 6200 A 800 800 0 0 1 4150 7000',
    'M 8000 6200 A 800 800 0 0 1 8800 7000',
    'M 13500 6200 A 800 800 0 0 1 14300 7000',
  ];

  /* ── furniture pieces ──────────────────────────────────────────────── */
  const furn = [
    /* Reception desk */
    { x: 800, y: 500, w: 3200, h: 600 },
    /* Waiting-area chairs */
    { x: 500, y: 2700, w: 500, h: 500 }, { x: 1300, y: 2700, w: 500, h: 500 }, { x: 2100, y: 2700, w: 500, h: 500 },
    { x: 500, y: 3400, w: 500, h: 500 }, { x: 1300, y: 3400, w: 500, h: 500 }, { x: 2100, y: 3400, w: 500, h: 500 },
    /* Meeting 10pax table */
    { x: 5800, y: 1100, w: 2400, h: 1400 },
    /* Meeting 6pax table */
    { x: 9800, y: 1300, w: 1600, h: 1000 },
    /* Phone-booth desks */
    { x: 13000, y: 600, w: 800, h: 500 }, { x: 13000, y: 2500, w: 800, h: 500 },
    /* Cabin desks */
    { x: 600, y: 5600, w: 2000, h: 600 }, { x: 3800, y: 5600, w: 2000, h: 600 },
    { x: 6800, y: 5600, w: 2000, h: 600 }, { x: 9800, y: 5600, w: 1800, h: 600 },
    /* Discussion booth table */
    { x: 12800, y: 5200, w: 1400, h: 1000 },
    /* Workstation rows */
    { x: 600, y: 7300, w: 2400, h: 400 }, { x: 3400, y: 7300, w: 2400, h: 400 },
    { x: 600, y: 8100, w: 2400, h: 400 }, { x: 3400, y: 8100, w: 2400, h: 400 },
    { x: 600, y: 8900, w: 2400, h: 400 }, { x: 3400, y: 8900, w: 2400, h: 400 },
    /* Server racks */
    { x: 6800, y: 8800, w: 400, h: 1200 }, { x: 7400, y: 8800, w: 400, h: 1200 }, { x: 8000, y: 8800, w: 400, h: 1200 },
    /* Pantry counter */
    { x: 6800, y: 7200, w: 2400, h: 400 },
    /* Cafeteria tables */
    { x: 9800, y: 7200, w: 800, h: 800 }, { x: 11000, y: 7200, w: 800, h: 800 },
    /* Store shelves */
    { x: 9800, y: 8800, w: 2000, h: 400 },
  ];

  const legendItems = [
    { cls: 'wall',      stroke: wallC,  shape: { w: 12, h: 4, type: 'rect'  as const } },
    { cls: 'partition', stroke: partC,  shape: { w: 12, h: 4, type: 'dash'  as const } },
    { cls: 'door',      stroke: doorC,  shape: { w: 12, h: 4, type: 'rect'  as const } },
    { cls: 'furniture', stroke: furnC,  shape: { w: 12, h: 4, type: 'rect'  as const } },
  ];

  return (
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block' }}
        onClick={(e) => { if (e.target === e.currentTarget) onSelect(null); }}>
        <defs>
          <pattern id="grid5" x="0" y="0" width="48" height="48" patternUnits="userSpaceOnUse">
            <circle cx="0.5" cy="0.5" r="0.5" fill="var(--rule-strong)" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#grid5)" opacity={0.35} />

        {/* Room fills */}
        {rooms.map((r, i) => (
          <rect key={`rf${i}`} x={r.x} y={r.y} width={r.w} height={r.h}
            fill={fills[r.fi]} stroke="none" />
        ))}

        {/* Exterior walls */}
        <rect x="200" y="200" width="14600" height="9600"
          fill="none" stroke={wallC} strokeWidth="200" />

        {/* Interior partition walls */}
        {walls.map(([x1, y1, x2, y2], i) => (
          <line key={`wl${i}`} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={partC} strokeWidth="100" />
        ))}

        {/* Door arcs */}
        {doorPaths.map((d, i) => (
          <path key={`dr${i}`} d={d} fill="none" stroke={doorC}
            strokeWidth="60" strokeLinecap="round" />
        ))}

        {/* Furniture */}
        {furn.map((f, i) => (
          <rect key={`fn${i}`} x={f.x} y={f.y} width={f.w} height={f.h}
            fill="rgba(90,87,78,0.12)" stroke={furnC} strokeWidth="50" rx={80} />
        ))}

        {/* Room labels */}
        {rooms.map((r, i) => (
          <text key={`lb${i}`} x={r.lx} y={r.ly}
            textAnchor="middle" dominantBaseline="central"
            fontFamily="var(--font-body)" fontSize="350" fontWeight="500"
            fill="var(--ink-2)" style={{ pointerEvents: 'none' }}>
            {r.name.split('\n').map((line, j) => (
              <tspan key={j} x={r.lx} dy={j === 0 ? 0 : 420}>{line}</tspan>
            ))}
          </text>
        ))}

        {/* Dimension scale bar */}
        <line x1="200" y1="9900" x2="5200" y2="9900" stroke="var(--ink-3)" strokeWidth="40" />
        <line x1="200" y1="9850" x2="200"   y2="9950" stroke="var(--ink-3)" strokeWidth="40" />
        <line x1="5200" y1="9850" x2="5200" y2="9950" stroke="var(--ink-3)" strokeWidth="40" />
        <text x="2700" y="9830" textAnchor="middle" fontFamily="var(--font-mono)"
          fontSize="220" fill="var(--ink-3)">3,000 mm</text>
      </svg>

      {/* Legend */}
      <div style={{
        position: 'absolute', left: 12, bottom: 12,
        background: 'var(--paper)', border: '1px solid var(--rule-strong)',
        padding: '12px 14px', fontSize: 11,
      }}>
        <div className="kicker" style={{ marginBottom: 6 }}>Legend</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 10px' }}>
          {legendItems.map((l) => (
            <Row key={l.cls} shape={l.shape} stroke={l.stroke}
              label={l.cls.charAt(0).toUpperCase() + l.cls.slice(1)} />
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Legend row helper
   ───────────────────────────────────────────────────────────────────────── */

function Row({ shape, stroke, label }: { shape: { w: number; h: number; type: 'rect' | 'dash' | 'accent' }; stroke: string; label: string }) {
  const color = shape.type === 'accent' ? 'var(--accent)' : stroke;
  const dash = shape.type === 'dash' ? '6,4' : undefined;
  return (
    <>
      <span style={{
        width: shape.w, height: shape.h,
        background: shape.type === 'accent' ? color : 'transparent',
        border: `1.5px ${dash ? 'dashed' : 'solid'} ${color}`,
        alignSelf: 'center',
      }} />
      <span style={{ textTransform: 'capitalize' }}>{label}</span>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Plan3D — 3-D viewer with demo office fallback
   ───────────────────────────────────────────────────────────────────────── */

function Plan3D({ objects, onSelect }: { objects: DetectedObject[]; onSelect: (id: number | null) => void }) {
  const scaledObjects = useMemo(() =>
    objects.map((o) => ({
      ...o,
      bbox_x: o.bbox_x * 15000,
      bbox_y: o.bbox_y * 10000,
      length: o.length * 15000,
      width:  o.width  * 10000,
    })),
  [objects]);

  const hasObjects = objects.length > 0;

  return (
    <Canvas shadows camera={{ position: [12, 10, 12], fov: 45 }} style={{ background: 'var(--paper)' }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[15, 22, 10]} intensity={1.1} castShadow />
      <directionalLight position={[-12, 6, -10]} intensity={0.4} />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[hasObjects ? 40 : 16, hasObjects ? 40 : 11]} />
        <meshStandardMaterial color={hasObjects ? 'var(--paper-2)' : '#D7D2C2'} />
      </mesh>

      {hasObjects ? (
        /* ── Real detected objects ────────────────────────────────────── */
        scaledObjects.slice(0, 80).map((o, i) => {
          const scale = 0.04;
          const x = (o.bbox_x - 5000) * scale + (i % 8 - 4) * 1.2;
          const z = (o.bbox_y - 5000) * scale + (Math.floor(i / 8) - 4) * 1.2;
          const w = Math.max(0.5, o.length * scale);
          const d = Math.max(0.5, o.width * scale);
          const s = OBJECT_STYLE[categorizeObjectType(o.object_type)];
          const h = Math.max(0.5, s.height3d);
          return (
            <mesh key={o.id} position={[x, h / 2, z]} castShadow receiveShadow
              onClick={(e) => { e.stopPropagation(); onSelect(o.id); }}>
              <boxGeometry args={[w, h, d]} />
              <meshStandardMaterial color={s.tone} roughness={0.6} metalness={0.05} />
            </mesh>
          );
        })
      ) : (
        /* ── Demo 3-D office ──────────────────────────────────────────── */
        <>
          {/* Perimeter walls */}
          <DemoWall pos={[0, 1.3, -5]}    size={[15, 2.6, 0.15]} />
          <DemoWall pos={[0, 1.3, 5]}     size={[15, 2.6, 0.15]} />
          <DemoWall pos={[-7.5, 1.3, 0]}  size={[0.15, 2.6, 10]} />
          <DemoWall pos={[7.5, 1.3, 0]}   size={[0.15, 2.6, 10]} />

          {/* Horizontal partitions (z ≈ row dividers) */}
          <DemoWall pos={[0, 1.25, -1]}     size={[15, 2.5, 0.08]} />
          <DemoWall pos={[0, 1.25, 2]}      size={[15, 2.5, 0.08]} />
          <DemoWall pos={[10.65, 1.25, 3.5]} size={[8.3, 2.5, 0.08]} />

          {/* Vertical partitions — row 1 (front) */}
          <DemoWall pos={[-2.5, 1.25, -3]} size={[0.08, 2.5, 4]} />
          <DemoWall pos={[1.5, 1.25, -3]}  size={[0.08, 2.5, 4]} />
          <DemoWall pos={[4.7, 1.25, -3]}  size={[0.08, 2.5, 4]} />

          {/* Vertical partitions — row 2 (middle) */}
          <DemoWall pos={[-4, 1.25, 0.5]}  size={[0.08, 2.5, 3]} />
          <DemoWall pos={[-1, 1.25, 0.5]}  size={[0.08, 2.5, 3]} />
          <DemoWall pos={[2, 1.25, 0.5]}   size={[0.08, 2.5, 3]} />
          <DemoWall pos={[4.7, 1.25, 0.5]} size={[0.08, 2.5, 3]} />

          {/* Vertical partitions — row 3 (back) */}
          <DemoWall pos={[-1, 1.25, 3.5]}  size={[0.08, 2.5, 3]} />
          <DemoWall pos={[2, 1.25, 3.5]}   size={[0.08, 2.5, 3]} />
          <DemoWall pos={[4.7, 1.25, 3.5]} size={[0.08, 2.5, 3]} />

          {/* Furniture — reception desk */}
          <DemoFurn pos={[-5.2, 0.35, -4.1]} size={[3, 0.7, 0.6]} />

          {/* Meeting tables */}
          <DemoFurn pos={[-0.5, 0.4, -3.2]} size={[2, 0.8, 1.2]} />
          <DemoFurn pos={[3, 0.4, -3.2]}    size={[1.4, 0.8, 0.8]} />

          {/* Cabin desks */}
          <DemoFurn pos={[-5.5, 0.35, 0.5]} size={[1.8, 0.7, 0.6]} />
          <DemoFurn pos={[-3, 0.35, 0.5]}   size={[1.8, 0.7, 0.6]} />
          <DemoFurn pos={[0.5, 0.35, 0.5]}  size={[1.8, 0.7, 0.6]} />
          <DemoFurn pos={[3.5, 0.35, 0.5]}  size={[1.6, 0.7, 0.6]} />

          {/* Workstation desks */}
          <DemoFurn pos={[-5, 0.35, 3]}   size={[2.4, 0.7, 0.4]} />
          <DemoFurn pos={[-2, 0.35, 3]}   size={[2.4, 0.7, 0.4]} />
          <DemoFurn pos={[-5, 0.35, 4]}   size={[2.4, 0.7, 0.4]} />
          <DemoFurn pos={[-2, 0.35, 4]}   size={[2.4, 0.7, 0.4]} />

          {/* Server racks */}
          <mesh position={[0, 0.6, 4.2]} castShadow receiveShadow>
            <boxGeometry args={[0.4, 1.2, 1]} />
            <meshStandardMaterial color="#1A1815" roughness={0.5} metalness={0.3} />
          </mesh>
          <mesh position={[0.6, 0.6, 4.2]} castShadow receiveShadow>
            <boxGeometry args={[0.4, 1.2, 1]} />
            <meshStandardMaterial color="#1A1815" roughness={0.5} metalness={0.3} />
          </mesh>
          <mesh position={[1.2, 0.6, 4.2]} castShadow receiveShadow>
            <boxGeometry args={[0.4, 1.2, 1]} />
            <meshStandardMaterial color="#1A1815" roughness={0.5} metalness={0.3} />
          </mesh>

          {/* Pantry counter */}
          <DemoFurn pos={[0, 0.4, 2.8]} size={[2.4, 0.8, 0.4]} tone="#888888" />

          {/* Cafeteria tables */}
          <DemoFurn pos={[3, 0.35, 2.8]}  size={[0.8, 0.7, 0.8]} />
          <DemoFurn pos={[4.2, 0.35, 2.8]} size={[0.8, 0.7, 0.8]} />
        </>
      )}

      <axesHelper args={[3]} position={[-12, 0, -12]} />
      <OrbitControls autoRotate autoRotateSpeed={0.4} enableDamping />
    </Canvas>
  );
}

/* ── tiny helpers for the demo 3-D scene ────────────────────────────── */

function DemoWall({ pos, size }: { pos: [number, number, number]; size: [number, number, number] }) {
  return (
    <mesh position={pos} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color="#F5F0E8" roughness={0.7} />
    </mesh>
  );
}

function DemoFurn({ pos, size, tone }: { pos: [number, number, number]; size: [number, number, number]; tone?: string }) {
  return (
    <mesh position={pos} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={tone ?? '#5A574E'} roughness={0.6} metalness={0.05} />
    </mesh>
  );
}
