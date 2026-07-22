import { useEffect, useState } from 'react';
import { Outlet, NavLink, useLocation, useParams } from 'react-router-dom';
import { useAuthStore } from '../store';

const PROJECT_TABS = [
  { segment: 'plan',       label: 'Plan',       hint: '02' },
  { segment: 'quantities', label: 'Quantities', hint: '03' },
  { segment: 'materials',  label: 'Materials',  hint: '04' },
  { segment: 'costs',      label: 'Costs',      hint: '05' },
  { segment: 'ai',         label: 'AI',         hint: '06' },
  { segment: 'export',     label: 'Export',     hint: '07' },
];

export default function Shell() {
  const user = useAuthStore((s) => s.user);
  const loc = useLocation();
  const { projectId } = useParams();
  const inProject = !!projectId;

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '240px 1fr',
      gridTemplateRows: '52px 1fr',
      gridTemplateAreas: '"side top" "side main"',
      height: '100vh',
      background: 'var(--paper)',
      color: 'var(--ink)',
    }}>
      {/* ── Top bar ── */}
      <header style={{
        gridArea: 'top',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        borderBottom: '1px solid var(--rule-strong)',
        background: 'var(--paper)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="kicker">File</span>
          <Crumb path={loc.pathname} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Clock />
          <span className="dot dot-active" />
          <span className="kicker">Live</span>
          <span style={{ borderLeft: '1px solid var(--rule)', height: 22 }} />
          <span className="kicker">Estimator</span>
          <div style={{
            width: 28, height: 28,
            borderRadius: '50%',
            background: 'var(--ink)',
            color: 'var(--accent)',
            fontFamily: 'var(--font-display)',
            fontSize: 14, fontWeight: 500,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid var(--ink)',
          }}>
            {(user?.name ?? '?').charAt(0)}
          </div>
        </div>
      </header>

      {/* ── Sidebar ── */}
      <aside style={{
        gridArea: 'side',
        borderRight: '1px solid var(--rule-strong)',
        background: 'var(--paper)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ padding: '20px 20px 28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <svg width="36" height="36" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" fill="var(--ink)" />
              <path d="M6 24 L11 14 L17 22 L26 6" stroke="var(--accent)" strokeWidth="2" fill="none" />
              <circle cx="6" cy="24" r="1.8" fill="var(--accent)" />
              <circle cx="11" cy="14" r="1.8" fill="var(--accent)" />
              <circle cx="17" cy="22" r="1.8" fill="var(--accent)" />
              <circle cx="26" cy="6" r="1.8" fill="var(--accent)" />
            </svg>
            <div>
              <div className="display" style={{ fontSize: 22, lineHeight: 1, fontWeight: 500 }}>
                Auto<em>Cost</em>
              </div>
              <div className="kicker" style={{ marginTop: 4 }}>Engine · v1.1</div>
            </div>
          </div>
        </div>

        <nav style={{ padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span className="kicker" style={{ padding: '8px 10px 12px' }}>Workspace</span>
          <SideLink to="/projects" label="Projects" hint="01" end />
          {inProject && PROJECT_TABS.map((t) => (
            <SideLink key={t.segment} to={`/projects/${projectId}/${t.segment}`} {...t} />
          ))}
        </nav>

        <div style={{ marginTop: 'auto', padding: '20px', borderTop: '1px solid var(--rule)' }}>
          <div className="tick">signed · Jasfo / Mudar</div>
          <div className="display" style={{ fontSize: 14, marginTop: 4, color: 'var(--ink-3)' }}>
            <em>estimation</em>, automated.
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{ gridArea: 'main', overflow: 'auto' }}>
        <Outlet />
      </main>
    </div>
  );
}

function Clock() {
  const [tick, setTick] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTick(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  const time = tick.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
  const date = tick.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  return <span className="num" style={{ fontSize: 12, color: 'var(--ink-3)' }}>{date} · {time} IST</span>;
}

function Crumb({ path }: { path: string }) {
  const parts = path.split('/').filter(Boolean);
  if (parts.length === 0) return <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>root</span>;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
      {parts.map((p, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {i > 0 && <span style={{ color: 'var(--ink-4)' }}>/</span>}
          <span style={{ color: i === parts.length - 1 ? 'var(--ink)' : 'var(--ink-2)' }}>{p}</span>
        </span>
      ))}
    </div>
  );
}

function SideLink({ to, label, hint, end }: { to: string; label: string; hint: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end ?? false}
      style={({ isActive }) => ({
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 10px',
        borderRadius: 'var(--r-md)',
        textDecoration: 'none',
        color: isActive ? 'var(--accent-ink)' : 'var(--ink-2)',
        background: isActive ? 'var(--accent)' : 'transparent',
        border: '1px solid',
        borderColor: isActive ? 'var(--ink)' : 'transparent',
        boxShadow: isActive ? '2px 2px 0 0 var(--ink)' : 'none',
        fontSize: 13,
        fontWeight: 500,
        transition: 'all var(--t-fast) var(--ease)',
        cursor: 'pointer',
      })}
    >
      <span className="num" style={{ fontSize: 9, color: 'currentColor', opacity: 0.5, width: 22 }}>{hint}</span>
      <span>{label}</span>
    </NavLink>
  );
}
