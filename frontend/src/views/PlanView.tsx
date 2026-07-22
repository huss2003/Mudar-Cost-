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

  if (!scaledObjects.length || !projection) {
    return (
      <div ref={containerRef} style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-3)', textAlign: 'center' }}>
        <div>
          <div style={{ width: 80, height: 80, border: '1px dashed var(--rule-strong)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', background: 'var(--paper)' }}>
            <svg width="36" height="36" viewBox="0 0 32 32" fill="none"><path d="M6 26 L11 16 L17 24 L26 8" stroke="var(--ink-3)" strokeWidth="1.5" fill="none" /></svg>
          </div>
          <div className="kicker">Awaiting plan</div>
          <div className="display" style={{ fontSize: 22, fontStyle: 'italic', marginTop: 4 }}>drop a drawing to begin</div>
        </div>
      </div>
    );
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

function Plan3D({ objects, onSelect }: { objects: DetectedObject[]; onSelect: (id: number | null) => void }) {
  /* Convert normalised 0-1 bbox coordinates to mm scale */
  const scaledObjects = useMemo(() =>
    objects.map((o) => ({
      ...o,
      bbox_x: o.bbox_x * 15000,
      bbox_y: o.bbox_y * 10000,
      length: o.length * 15000,
      width:  o.width  * 10000,
    })),
  [objects]);

  return (
    <Canvas shadows camera={{ position: [12, 10, 12], fov: 45 }} style={{ background: 'var(--paper)' }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[15, 22, 10]} intensity={1.1} castShadow />
      <directionalLight position={[-12, 6, -10]} intensity={0.4} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="var(--paper-2)" />
      </mesh>

      {scaledObjects.slice(0, 80).map((o, i) => {
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
      })}

      <axesHelper args={[3]} position={[-12, 0, -12]} />
      <OrbitControls autoRotate autoRotateSpeed={0.4} enableDamping />
    </Canvas>
  );
}
