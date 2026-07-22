import { useEffect, useMemo, useState } from 'react';
import { useProjectStore } from '../store';
import { computeQuantities, fetchBOQ } from '../api/boq';
import Empty from '../components/Empty';
import { formatINR } from '../ui/format';
import type { BOQLineItem } from '../types';

export default function QuantitiesView() {
  const project = useProjectStore((s) => s.currentProject);
  const [items, setItems] = useState<BOQLineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState<'idle' | 'computing'>('idle');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    if (!project) return;
    setLoading(true);
    fetchBOQ(project.id)
      .then((r) => setItems(r.trades))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [project?.id]);

  async function recompute() {
    if (!project) return;
    setPhase('computing');
    try {
      await computeQuantities(project.id);
      const r = await fetchBOQ(project.id);
      setItems(r.trades);
    } finally { setPhase('idle'); }
  }

  const byTrade = useMemo<{ trade: string; items: BOQLineItem[]; total: number }[]>(() => {
    const map: Record<string, { trade: string; items: BOQLineItem[]; total: number }> = {};
    for (const it of items) {
      const trade = it.trade ?? 'Misc';
      (map[trade] ??= { trade, items: [], total: 0 }).items.push(it);
      if (map[trade]) map[trade].total += it.total ?? 0;
    }
    return Object.values(map);
  }, [items]);

  const filtered = filter
    ? byTrade.filter((b) => b.trade.toLowerCase().includes(filter.toLowerCase()))
    : byTrade;

  return (
    <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 32px', borderBottom: '1px solid var(--rule-strong)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="kicker">Bill of quantities</span>
          <span className="badge">{items.length} items</span>
          <span className="badge">{byTrade.length} trades</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input
            className="field"
            placeholder="Filter by trade…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: 220 }}
          />
          <button className="btn btn-secondary" type="button" onClick={recompute} disabled={phase === 'computing'}>
            {phase === 'computing' ? 'Computing…' : 'Recompute ⌘↵'}
          </button>
        </div>
      </div>

      <div style={{ overflow: 'auto', padding: '24px 32px' }}>
        {loading ? (
          <Skeleton />
        ) : items.length === 0 ? (
          <Empty title="quantities not yet computed" hint="upload a floor plan then run Compute quantities" />
        ) : (
          <div className="draw-in">
            {filtered.map(({ trade, items: items_, total }) => (
              <section key={trade} style={{ marginBottom: 32 }}>
                <div style={{
                  display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
                  paddingBottom: 8, borderBottom: '2px solid var(--ink)', marginBottom: 0,
                }}>
                  <h2 className="display" style={{ fontSize: 28, fontWeight: 500 }}>
                    {trade}
                    <span style={{ color: 'var(--ink-3)', marginLeft: 10 }} className="num">·</span>
                    <span style={{ color: 'var(--ink-3)', marginLeft: 10, fontStyle: 'italic', fontFamily: 'var(--font-display)' }}>
                      {items_.length} items
                    </span>
                  </h2>
                  <div className="num" style={{ fontSize: 22, fontWeight: 500 }}>
                    <span className="rupee-pre">₹</span>{formatINR(total, { round: true })}
                  </div>
                </div>
                <table className="draft-table">
                  <thead>
                    <tr>
                      <th style={{ width: 32 }}>#</th>
                      <th>Description</th>
                      <th style={{ width: 80 }}>Unit</th>
                      <th style={{ width: 100, textAlign: 'right' }}>Qty</th>
                      <th style={{ width: 120, textAlign: 'right' }}>Rate</th>
                      <th style={{ width: 140, textAlign: 'right' }}>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items_.map((it, idx) => (
                      <tr key={it.id}>
                        <td><span className="num muted">{idx + 1}</span></td>
                        <td>
                          <div>{it.description}</div>
                          {it.location && <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>{it.location}</div>}
                          {it.material_name && (
                            <div style={{ fontSize: 11, color: 'var(--leaf)', marginTop: 2 }}>
                              <span className="dot dot-active" /> {it.material_name}
                            </div>
                          )}
                        </td>
                        <td className="num">{it.unit}</td>
                        <td className="num" style={{ textAlign: 'right' }}>{it.quantity}</td>
                        <td className="num" style={{ textAlign: 'right', color: 'var(--ink-2)' }}>
                          {it.rate ? <><span style={{ color: 'var(--ink-4)' }}>₹</span>{formatINR(it.rate)}</> : '—'}
                        </td>
                        <td className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
                          {it.total ? <><span style={{ color: 'var(--ink-4)' }}>₹</span>{formatINR(it.total)}</> : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {Array.from({ length: 6 }).map((_, i) => <div key={i} className="sk" style={{ height: 36 }} />)}
    </div>
  );
}
