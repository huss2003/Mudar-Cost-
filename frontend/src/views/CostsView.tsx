import { useEffect, useState } from 'react';
import { useProjectStore, selectProjectTotal } from '../store';
import { fetchCostSummary, fetchCostVersions } from '../api/costs';
import Empty from '../components/Empty';
import { formatINR, fmtDateTime } from '../ui/format';
import type { CostVersionSummary, TradeCostGroup } from '../types';

export default function CostsView() {
  const project = useProjectStore((s) => s.currentProject);
  const storeTotal = useProjectStore(selectProjectTotal);
  const [trades, setTrades] = useState<TradeCostGroup[]>([]);
  const [versions, setVersions] = useState<CostVersionSummary[]>([]);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!project) return;
    setLoading(true);
    Promise.all([fetchCostSummary(project.id), fetchCostVersions(project.id)])
      .then(([s, v]) => {
        setTrades(s.trades);
        setVersions(v);
        if (v.length > 0) setActiveVersion(v[v.length - 1].id);
      })
      .catch(() => { setTrades([]); setVersions([]); })
      .finally(() => setLoading(false));
  }, [project?.id]);

  const { total, maxT } = trades.reduce(
    (acc, t) => ({ total: acc.total + t.total, maxT: Math.max(acc.maxT, t.total) }),
    { total: 0, maxT: 1 },
  );
  // Prefer cost-version total (data has trade-level rates); fall back to live BOQ sum.
  const grand = total || storeTotal;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', height: '100%' }}>
      <aside style={{ borderRight: '1px solid var(--rule-strong)', padding: '32px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <div className="kicker">Project total</div>
          <div style={{ marginTop: 8 }}>
            <span className="num-display" style={{ fontSize: 64, lineHeight: 0.9 }}>
              <span className="rupee-pre">₹</span>{formatINR(grand, { round: true })}
            </span>
          </div>
          <div className="kicker" style={{ marginTop: 12 }}>inclusive of all trades · taxes excluded</div>
        </div>

        <hr className="hr" />

        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>Cost versions</div>
          {versions.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No versions saved yet. Live total updates as you select materials.</div>}
          {versions.map((v) => (
            <button key={v.id} onClick={() => setActiveVersion(v.id)} type="button" className="paper" style={{
              display: 'block', width: '100%',
              padding: '10px 12px', marginBottom: 6,
              background: v.id === activeVersion ? 'var(--accent)' : 'transparent',
              color: v.id === activeVersion ? 'var(--accent-ink)' : 'var(--ink)',
              border: '1px solid',
              borderColor: v.id === activeVersion ? 'var(--ink)' : 'var(--rule-strong)',
              cursor: 'pointer',
              textAlign: 'left',
              fontFamily: 'inherit',
              boxShadow: v.id === activeVersion ? '2px 2px 0 0 var(--ink)' : 'none',
            }}>
              <div className="display" style={{ fontSize: 18, fontWeight: 500 }}>{v.version_label}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
                <span style={{ fontSize: 11, color: 'currentColor', opacity: 0.7 }}>{fmtDateTime(v.created_at)}</span>
                <span className="num" style={{ fontSize: 14, fontWeight: 500 }}>
                  <span className="rupee-pre">₹</span>{formatINR(v.total, { round: true })}
                </span>
              </div>
            </button>
          ))}
        </div>

        <hr className="hr" />

        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>Cost lever</div>
          <div className="display" style={{ fontSize: 22, fontStyle: 'italic', lineHeight: 1.2 }}>swap a material and watch</div>
          <div className="display" style={{ fontSize: 22, fontStyle: 'italic', lineHeight: 1.2 }}>this total move <em>in real time</em>.</div>
        </div>
      </aside>

      <div style={{ overflow: 'auto', padding: '32px' }}>
        <div className="draw-in">
          <div className="kicker" style={{ marginBottom: 8 }}>Trade breakdown</div>
          <h2 className="display" style={{ fontSize: 40, fontWeight: 500 }}>how the<em> money</em> is split.</h2>

          {loading ? <div className="muted" style={{ marginTop: 32 }}>Loading…</div>
            : trades.length === 0
              ? <div style={{ marginTop: 32 }}><Empty title="no costs recorded yet" hint="compute quantities to begin" /></div>
              : (
                <div style={{ marginTop: 32 }}>
                  {trades.map((t) => (
                    <div className="bar-row" key={t.trade}>
                      <div>
                        <div className="bar-label">{t.trade}</div>
                        <div className="kicker" style={{ marginTop: 2 }}>{t.count} items</div>
                      </div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: `${Math.max(2, (t.total / maxT) * 100)}%` }} />
                      </div>
                      <div className="num" style={{ fontSize: 18, textAlign: 'right', fontWeight: 500 }}>
                        <span className="rupee-pre">₹</span>{formatINR(t.total, { round: true })}
                      </div>
                    </div>
                  ))}

                  <div style={{
                    display: 'grid', gridTemplateColumns: '220px 1fr 120px', gap: 16,
                    marginTop: 24, padding: '16px 0',
                    borderTop: '2px solid var(--ink)',
                    background: 'var(--accent)',
                    marginInline: '-32px',
                    paddingInline: '32px',
                  }}>
                    <div className="display" style={{ fontSize: 28, fontWeight: 500, color: 'var(--accent-ink)' }}>Total</div>
                    <div />
                    <div className="num" style={{ fontSize: 28, fontWeight: 600, textAlign: 'right', color: 'var(--accent-ink)' }}>
                      <span className="rupee-pre">₹</span>{formatINR(grand, { round: true })}
                    </div>
                  </div>
                </div>
              )}
        </div>
      </div>
    </div>
  );
}
