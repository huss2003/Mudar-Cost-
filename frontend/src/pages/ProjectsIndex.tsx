import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchProjects, createProject } from '../api/projects';
import { uploadDrawing, replaceDrawingFile } from '../api/drawings';
import { pollDrawingUntilReady } from '../api/sse';
import { convertPdfToImages } from '../utils/pdfToImage';
import type { Project } from '../types';
import { STATUS_LABELS, STATUS_DOT } from '../types';
import { formatINR, pad3 } from '../ui/format';
import Empty from '../components/Empty';
import Skeleton from '../components/Skeleton';

export default function ProjectsIndex() {
  const nav = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPhase, setUploadPhase] = useState('');
  const [progress, setProgress] = useState<{ current: number; total: number; page?: number; totalPages?: number }>({ current: 0, total: 0 });
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try { setProjects(await fetchProjects()); }
    catch { setProjects([]); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const totals = useMemo(() => ({
    total:      projects.length,
    inProgress: projects.filter((p) => p.status === 'in_progress' || p.status === 'priced').length,
    sent:       projects.filter((p) => p.status === 'sent').length,
    drawings:   projects.filter((p) => p.drawings_count > 0).length,
  }), [projects]);

  function isPdf(file: File): boolean {
    return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  }

  async function onFiles(files: FileList) {
    if (uploading) return; // Block duplicate uploads
    const file = files[0];
    if (!file) return;
    setUploading(true);
    setProgress({ current: 0, total: 0 });
    try {
      const projectName = file.name.replace(/\.[^.]+$/, '');

      if (isPdf(file)) {
        // Step 1: Create project + upload PDF
        setUploadPhase('Uploading PDF…');
        setProgress({ current: 1, total: 4 });
        const proj = await createProject({ name: projectName });
        const res = await uploadDrawing(file, proj.id);
        const drawingId = res.drawing_id;

        // Step 2: Convert PDF → PNG (with progress)
        setUploadPhase('Converting to PNG…');
        setProgress({ current: 2, total: 4 });
        const pngFiles = await convertPdfToImages(file, 1.5, (page, total) => {
          setProgress({ current: 2, total: 4, page, totalPages: total });
        });
        if (pngFiles.length === 0) throw new Error('PDF conversion produced no pages');

        // Step 3: Upload PNG
        setUploadPhase('Uploading PNG…');
        setProgress({ current: 3, total: 4 });
        await replaceDrawingFile(drawingId, pngFiles[0]);

        // Step 4: Detect
        setUploadPhase('Detecting objects…');
        setProgress({ current: 4, total: 4 });
        await pollDrawingUntilReady(drawingId, { attempts: 60, intervalMs: 1000 });

        nav(`/projects/${proj.id}/plan`);
      } else {
        // Non-PDF flow
        setUploadPhase('Uploading…');
        setProgress({ current: 1, total: 2 });
        const proj = await createProject({ name: projectName });
        const res = await uploadDrawing(file, proj.id);

        setUploadPhase('Detecting objects…');
        setProgress({ current: 2, total: 2 });
        await pollDrawingUntilReady(res.drawing_id, { attempts: 60, intervalMs: 1000 });

        nav(`/projects/${proj.id}/plan`);
      }
    } catch (err: any) {
      alert(`Upload failed: ${err?.message ?? err}`);
    } finally {
      setUploading(false);
      setUploadPhase('');
      setProgress({ current: 0, total: 0 });
    }
  }

  const progressPct = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div style={{ padding: '36px 48px', maxWidth: 1280, margin: '0 auto' }}>
      <div className="draw-in">
        <div className="kicker" style={{ marginBottom: 12 }}>Workspace · Index</div>
        <h1 className="display" style={{ fontSize: 64, fontWeight: 400, lineHeight: 0.9 }}>
          Projects<br /><em style={{ fontStyle: 'italic' }}>in flight.</em>
        </h1>
        <p style={{ marginTop: 20, fontSize: 16, color: 'var(--ink-2)', maxWidth: 540, lineHeight: 1.5 }}>
          Upload a floor plan and watch the engine produce a bill of quantities, a costed BOQ,
          and a client-ready proposal in seconds — not days.
        </p>
      </div>

      <div className="draw-in" style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 0, border: '1px solid var(--rule-strong)',
        marginTop: 36, background: 'var(--paper)',
      }}>
        <Stat n={totals.total}      label="Active projects" hint="All time" />
        <Stat n={totals.inProgress} label="In progress"     hint="Being priced" />
        <Stat n={totals.sent}       label="Sent to client"  hint="Awaiting decision" />
        <Stat n={totals.drawings}   label="Drawings"        hint="On record" />
      </div>

      {/* Upload dropzone / progress */}
      {uploading ? (
        <div style={{
          marginTop: 36, padding: '48px 40px',
          border: '2px dashed var(--accent)',
          background: 'rgba(202, 239, 118, 0.08)',
          position: 'relative', overflow: 'hidden',
        }}>
          {/* Step indicator */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 32, marginBottom: 24 }}>
            {['Upload', 'Convert', 'Detect', 'Done'].map((label, i) => {
              const step = i + 1;
              const active = progress.current === step;
              const done = progress.current > step;
              return (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: '50%',
                    border: `2px solid ${done ? 'var(--accent)' : active ? 'var(--ink)' : 'var(--rule-strong)'}`,
                    background: done ? 'var(--accent)' : active ? 'var(--ink)' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 12, fontWeight: 700,
                    color: done ? 'var(--ink)' : active ? 'var(--paper)' : 'var(--ink-3)',
                  }}>
                    {done ? '✓' : step}
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 500, color: done || active ? 'var(--ink)' : 'var(--ink-3)' }}>
                    {label}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Progress bar */}
          <div style={{
            width: '100%', height: 6, background: 'var(--rule)',
            borderRadius: 3, overflow: 'hidden', marginBottom: 16,
          }}>
            <div style={{
              width: `${progressPct}%`, height: '100%',
              background: 'var(--accent)',
              borderRadius: 3, transition: 'width 0.3s ease',
            }} />
          </div>

          {/* Status text */}
          <div style={{ textAlign: 'center' }}>
            <div className="display" style={{ fontSize: 22, fontStyle: 'italic' }}>
              {uploadPhase}
            </div>
            {progress.page && progress.totalPages && (
              <div className="kicker" style={{ marginTop: 8 }}>
                Page {progress.page} of {progress.totalPages}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div
          className="dropzone draw-in"
          data-dragging={dragging}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files) onFiles(e.dataTransfer.files); }}
          onClick={() => fileInput.current?.click()}
          style={{ marginTop: 36, padding: '48px 24px', cursor: 'pointer' }}
        >
          <input ref={fileInput} type="file" accept=".dwg,.dxf,.pdf,.png,.jpg,.jpeg" hidden
            onChange={(e) => e.target.files && onFiles(e.target.files)} />
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 60, height: 60,
              border: '2px dashed var(--rule-strong)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--paper)',
            }}>
              <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
                <path d="M6 26 L11 16 L17 24 L26 8" stroke="var(--ink)" strokeWidth="2" fill="none" />
                <circle cx="6" cy="26" r="2" fill="var(--accent)" />
                <circle cx="11" cy="16" r="2" fill="var(--accent)" />
                <circle cx="17" cy="24" r="2" fill="var(--accent)" />
                <circle cx="26" cy="8" r="2" fill="var(--accent)" />
              </svg>
            </div>
            <div>
              <div className="display" style={{ fontSize: 22, fontStyle: 'italic', color: 'var(--ink)' }}>
                drop a floor plan here
              </div>
              <div className="kicker" style={{ marginTop: 8 }}>
                .dwg · .dxf · .pdf · .png — accepted up to 50 MB
              </div>
            </div>
            <button className="btn btn-secondary" type="button">Choose file</button>
          </div>
        </div>
      )}

      <div className="draw-in" style={{ marginTop: 48 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <h2 className="display" style={{ fontSize: 32 }}>All <em>projects</em></h2>
          <button className="btn btn-ghost" onClick={load} type="button">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M2 7l3-3M2 7l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square"/>
            </svg>
            Refresh
          </button>
        </div>
        <hr className="hr" style={{ marginTop: 12, marginBottom: 0 }} />

        {loading ? (
          <Skeleton rows={5} variant="row" />
        ) : projects.length === 0 ? (
          <Empty title="nothing here yet" hint="drop a floor plan above to begin" />
        ) : (
          <div style={{ marginTop: 0 }}>
            {projects.map((p) => <ProjectRow key={p.id} p={p} onClick={() => nav(`/projects/${p.id}/plan`)} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ n, label, hint }: { n: number; label: string; hint: string }) {
  return (
    <div style={{ padding: '20px 24px', borderRight: '1px solid var(--rule)' }}>
      <div className="num-display" style={{ color: 'var(--ink)' }}>{n}</div>
      <div style={{ marginTop: 4, fontSize: 13, fontWeight: 500 }}>{label}</div>
      <div className="kicker" style={{ marginTop: 4 }}>{hint}</div>
    </div>
  );
}

function ProjectRow({ p, onClick }: { p: Project; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: '100%',
        display: 'grid',
        gridTemplateColumns: '60px 1.6fr 1fr 1fr 1fr 24px',
        gap: 16,
        alignItems: 'center',
        padding: '14px 4px',
        background: 'transparent',
        border: 'none',
        borderBottom: '1px solid var(--rule)',
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: 'inherit',
        color: 'var(--ink)',
        transition: 'background var(--t-fast) var(--ease)',
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(26,24,21,0.03)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
    >
      <span className="num" style={{ color: 'var(--ink-3)' }}>{pad3(p.id)}</span>
      <div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 500, letterSpacing: '-0.015em' }}>{p.name}</div>
        {p.client && <div className="kicker" style={{ marginTop: 2 }}>{p.client}</div>}
      </div>
      <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>{p.drawings_count} drawings</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span className={STATUS_DOT[p.status]} />
        <span style={{ fontSize: 12, color: 'var(--ink-2)', fontWeight: 500 }}>{STATUS_LABELS[p.status]}</span>
      </div>
      <div className="num" style={{ fontSize: 16, color: 'var(--ink)' }}>
        {p.total ? <><span className="rupee-pre">₹</span>{formatINR(p.total, { round: true })}</> : <span className="muted">—</span>}
      </div>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M5 2l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
      </svg>
    </button>
  );
}
