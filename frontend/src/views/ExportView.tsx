import { ReactNode, useEffect, useState } from 'react';
import { useProjectStore, selectProjectTotal } from '../store';
import { fetchBOQ } from '../api/boq';
import { generateProposal, generateExport, generatePurchaseList, generateClientPresentation, listExports } from '../api/exports';
import Empty from '../components/Empty';
import { formatINR, fmtDateTime } from '../ui/format';

interface Deliverable {
  key: string;
  title: string;
  sub: string;
  pitch: string;
  run: (projectId: number) => Promise<unknown>;
}

const DELIVERABLES: Deliverable[] = [
  { key: 'proposal', title: 'Proposal', sub: 'Cover, scope, payment terms, scope exclusions', pitch: 'What you send to the client to win the work.',
    run: (pid) => generateProposal(pid) },
  { key: 'xlsx', title: 'Costed BOQ · Excel', sub: 'Trades grouped, with totals', pitch: 'For the estimator who wants to negotiate per line.',
    run: (pid) => generateExport(pid, 'xlsx') },
  { key: 'pdf', title: 'Costed BOQ · PDF', sub: 'Print-ready', pitch: 'For the client who prefers paper.',
    run: (pid) => generateExport(pid, 'pdf') },
  { key: 'list', title: 'Purchase list', sub: 'Grouped by vendor', pitch: 'What procurement needs to send the orders.',
    run: (pid) => generatePurchaseList(pid) },
  { key: 'pres', title: 'Client presentation', sub: 'Branded slides with cost summary', pitch: 'For the kick-off meeting.',
    run: (pid) => generateClientPresentation(pid) },
];

export default function ExportView() {
  const project = useProjectStore((s) => s.currentProject);
  const total = useProjectStore(selectProjectTotal);
  const boqItems = useProjectStore((s) => s.boqItems);
  const setBoqItems = useProjectStore((s) => s.setBoqItems);
  const [busy, setBusy] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    if (!project) return;
    listExports(project.id).then(setHistory).catch(() => setHistory([]));
    fetchBOQ(project.id).then((boq) => { if (boq?.trades) setBoqItems(boq.trades); }).catch(() => {});
  }, [project?.id, setBoqItems]);

  async function run(d: Deliverable) {
    if (!project) return;
    setBusy(d.key);
    try {
      await d.run(project.id);
      setHistory(await listExports(project.id));
    } catch (e: any) {
      alert(`Export failed: ${e?.message ?? e}`);
    } finally { setBusy(null); }
  }

  const tradesCount = new Set(boqItems.map((i) => i.trade)).size;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', height: '100%', overflow: 'hidden' }}>
      <div style={{ overflow: 'auto', padding: '32px' }}>
        <div className="draw-in">
          <div className="kicker" style={{ marginBottom: 8 }}>Send it.</div>
          <h2 className="display" style={{ fontSize: 44, fontWeight: 500 }}>five formats<br /><em>leave this page with.</em></h2>
          <p className="muted" style={{ marginTop: 12, fontSize: 14, maxWidth: 520 }}>
            Every deliverable is generated from the current cost version. If you change a material after exporting, re-run before sending.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 32 }}>
            {DELIVERABLES.map((d) => (
              <DeliverableRow key={d.key} d={d} busy={busy === d.key} onRun={() => run(d)} />
            ))}
          </div>
        </div>
      </div>

      <aside style={{ borderLeft: '1px solid var(--rule-strong)', padding: '32px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 8 }}>Project total (so far)</div>
        <div className="num-display" style={{ fontSize: 48 }}>
          <span className="rupee-pre">₹</span>{formatINR(total, { round: true })}
        </div>
        <div className="kicker" style={{ marginTop: 4 }}>{boqItems.length} BOQ items · {tradesCount} trades</div>

        <hr className="hr" style={{ margin: '32px 0' }} />

        <div className="kicker" style={{ marginBottom: 8 }}>Recent exports</div>
        {history.length === 0 ? <RecentEmpty /> : <RecentList items={history} />}
      </aside>
    </div>
  );
}

function DeliverableRow({ d, busy, onRun }: { d: Deliverable; busy: boolean; onRun: () => void }) {
  return (
    <div className="paper" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 16, padding: '18px 20px' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <h3 className="display" style={{ fontSize: 22, fontWeight: 500 }}>{d.title}</h3>
          <span className="kicker">{d.sub}</span>
        </div>
        <div style={{ marginTop: 4, fontSize: 13, color: 'var(--ink-2)' }}>{d.pitch}</div>
      </div>
      <button className="btn btn-primary" type="button" onClick={onRun} disabled={busy}>
        {busy ? 'Generating…' : 'Generate →'}
      </button>
    </div>
  );
}

function RecentList({ items }: { items: any[] }) {
  return (
    <div>
      {items.slice(0, 12).map((e, i) => (
        <div key={e.id ?? i} style={{
          padding: '10px 0', borderBottom: '1px solid var(--rule)',
          display: 'grid', gridTemplateColumns: '1fr auto', gap: 12,
        }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>{e.title ?? e.kind ?? e.name ?? 'export'}</div>
            <div className="kicker" style={{ marginTop: 2 }}>
              {e.format ?? 'pdf'} · {e.created_at ? fmtDateTime(e.created_at) : ''}
            </div>
          </div>
          {e.download_url
            ? <a href={e.download_url} target="_blank" rel="noreferrer" className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 12 }}>Download</a>
            : <span className="kicker" style={{ color: 'var(--ink-3)' }}>ready</span>}
        </div>
      ))}
    </div>
  );
}

function RecentEmpty(): ReactNode {
  return <Empty title={<>nothing yet — <em>generate one.</em></>} />;
}
