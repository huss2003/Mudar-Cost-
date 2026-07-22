import { useEffect, useState } from 'react';
import { useParams, useLocation, useNavigate, Link } from 'react-router-dom';
import { fetchProject } from '../api/projects';
import { useProjectStore, selectProjectTotal, VIEW_IDS, type ViewMode } from '../store';
import { formatINR, pad3 } from '../ui/format';
import PlanView from '../views/PlanView';
import QuantitiesView from '../views/QuantitiesView';
import MaterialsView from '../views/MaterialsView';
import CostsView from '../views/CostsView';
import AIView from '../views/AIView';
import ExportView from '../views/ExportView';

const TABS: { id: ViewMode; label: string; index: string; Comp: React.ComponentType }[] = [
  { id: 'plan',       label: 'Plan',       index: '02', Comp: PlanView },
  { id: 'quantities', label: 'Quantities', index: '03', Comp: QuantitiesView },
  { id: 'materials',  label: 'Materials',  index: '04', Comp: MaterialsView },
  { id: 'costs',      label: 'Costs',      index: '05', Comp: CostsView },
  { id: 'ai',         label: 'AI',         index: '06', Comp: AIView },
  { id: 'export',     label: 'Export',     index: '07', Comp: ExportView },
];

export default function Workspace() {
  const { projectId } = useParams();
  const loc = useLocation();
  const nav = useNavigate();
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);
  const currentProject = useProjectStore((s) => s.currentProject);
  const total = useProjectStore(selectProjectTotal);
  const [bootError, setBootError] = useState<string | null>(null);

  const subpath = loc.pathname.split('/').slice(3).join('/');
  const view: ViewMode = (VIEW_IDS as readonly string[]).includes(subpath) ? (subpath as ViewMode) : 'plan';
  const ViewComp = TABS.find((t) => t.id === view)?.Comp ?? PlanView;

  useEffect(() => {
    const pid = Number(projectId);
    if (!Number.isFinite(pid) || pid <= 0) {
      setBootError(`Invalid project id: ${projectId}`);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12_000);
    fetchProject(pid)
      .then((p) => { setCurrentProject(p); setBootError(null); })
      .catch((e) => {
        if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') {
          setBootError('Project load timed out after 12s — the API is unreachable from this preview.');
        } else {
          setBootError(e?.message ?? 'Failed to load project');
        }
      })
      .finally(() => clearTimeout(timer));
    return () => ctrl.abort();
  }, [projectId, setCurrentProject]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px 32px 0',
        borderBottom: '1px solid var(--rule-strong)',
        background: 'var(--paper)',
      }}>
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            Project · {currentProject ? `№${pad3(currentProject.id)}` : bootError ? 'unavailable' : 'loading…'}
          </div>
          <h1 className="display" style={{ fontSize: 40, lineHeight: 1, fontWeight: 500 }}>
            {currentProject?.name ?? (bootError ? 'Project unavailable' : 'Loading…')}
            <span style={{ color: 'var(--ink-4)', fontStyle: 'italic', fontWeight: 300 }}>
              {currentProject?.client ? ` · ${currentProject.client}` : ''}
            </span>
          </h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <div style={{ textAlign: 'right' }}>
            <div className="kicker">Live total</div>
            <div className="num-display" style={{ marginTop: 4 }}>
              <span className="rupee-pre">₹</span>{formatINR(total, { round: true })}
            </div>
          </div>
          <button className="btn btn-secondary" type="button" onClick={() => nav('/projects')}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M12 7H2M12 7l-3-3M12 7l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
            </svg>
            All projects
          </button>
        </div>
      </header>

      <nav style={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        padding: '12px 32px 0',
        borderBottom: '1px solid var(--rule-strong)',
        background: 'var(--paper)',
      }}>
        {TABS.map((t) => (
          <Link
            key={t.id}
            to={`/projects/${projectId}/${t.id}`}
            className="tab"
            aria-selected={view === t.id}
          >
            <span className="num" style={{ fontSize: 9, opacity: 0.6 }}>{t.index}</span>
            {t.label}
          </Link>
        ))}
      </nav>

      <div className="draw-in" style={{ flex: 1, overflow: 'hidden' }}>
        {bootError
          ? <WorkspaceError message={bootError} />
          : <ViewComp />}
      </div>
    </div>
  );
}

function WorkspaceError({ message }: { message: string }) {
  return (
    <div style={{ padding: 64, textAlign: 'center' }}>
      <div className="display" style={{ fontSize: 32, fontStyle: 'italic' }}>project not loaded</div>
      <div className="kicker" style={{ marginTop: 12, color: 'var(--brick)' }}>{message}</div>
    </div>
  );
}
