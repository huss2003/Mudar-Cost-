import { useEffect, useMemo, useState } from 'react';
import { fetchMaterialsCatalog } from '../api/materials';
import Empty from '../components/Empty';
import { formatINR } from '../ui/format';
import type { Material } from '../types';

const SWATCH_TABLE: Array<{ test: RegExp; style: React.CSSProperties }> = [
  { test: /tile|floor/i,        style: { background: 'repeating-linear-gradient(45deg, var(--paper-2), var(--paper-2) 4px, var(--paper-3) 4px, var(--paper-3) 8px)' } },
  { test: /glass/i,             style: { background: 'linear-gradient(135deg, rgba(27,77,126,0.18), rgba(138,182,214,0.3))' } },
  { test: /wall|paint/i,        style: { background: 'linear-gradient(180deg, var(--paper-3), var(--paper-2))' } },
  { test: /carpet/i,            style: { background: 'repeating-linear-gradient(90deg, var(--paper-3), var(--paper-3) 2px, var(--paper-2) 2px, var(--paper-2) 4px)' } },
  { test: /light|electric/i,    style: { background: 'var(--ink)' } },
  { test: /./,                  style: { background: 'var(--paper-3)' } },
];

function swatchFor(category: string): React.CSSProperties {
  const fallback = SWATCH_TABLE[SWATCH_TABLE.length - 1].style;
  return (SWATCH_TABLE.find((row) => row.test.test(category)) ?? { style: fallback }).style;
}

export default function MaterialsView() {
  const [items, setItems] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    setLoading(true);
    fetchMaterialsCatalog({ limit: 200 }).then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, []);

  const { filtered, preferredCount } = useMemo(() => {
    const norm = q.toLowerCase();
    return {
      preferredCount: items.filter((m) => m.is_preferred).length,
      filtered: items.filter((m) =>
        !norm ||
        m.name.toLowerCase().includes(norm) ||
        m.brand.toLowerCase().includes(norm) ||
        m.category.toLowerCase().includes(norm),
      ),
    };
  }, [items, q]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 32px', borderBottom: '1px solid var(--rule-strong)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="kicker">Materials catalogue</span>
          <span className="badge">{filtered.length}</span>
          <span className="badge">{preferredCount} preferred</span>
        </div>
        <input className="field" placeholder="Search by name, brand, or category…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 320 }} />
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '24px 32px' }}>
        {loading ? <div className="muted">Loading…</div>
          : filtered.length === 0
            ? <Empty title="nothing matches" hint="clear your search or upload a new catalogue." />
            : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 16,
              }}>
                {filtered.map((m) => <MaterialCard key={m.id} m={m} />)}
              </div>
            )}
      </div>
    </div>
  );
}

function MaterialCard({ m }: { m: Material }) {
  return (
    <div className="paper" style={{ padding: 16, cursor: 'pointer', transition: 'all var(--t-fast) var(--ease)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLElement).style.boxShadow = '2px 2px 0 0 var(--ink)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.transform = ''; (e.currentTarget as HTMLElement).style.boxShadow = ''; }}
    >
      <div style={{ height: 80, margin: '-16px -16px 12px', ...swatchFor(m.category) }}>
        <div style={{
          background: 'var(--paper)', padding: '4px 8px',
          fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink)',
          display: 'inline-block', borderRight: '1px solid var(--ink)', borderBottom: '1px solid var(--ink)',
        }}>{m.category}</div>
        {m.is_preferred && (
          <span style={{
            position: 'absolute', right: 12, top: 12,
            background: 'var(--accent)', border: '1px solid var(--ink)',
            padding: '2px 6px', fontSize: 9, fontWeight: 600,
            textTransform: 'uppercase', letterSpacing: '0.1em',
          }}>Preferred</span>
        )}
      </div>
      <div className="display" style={{ fontSize: 18, fontWeight: 500, lineHeight: 1.2 }}>{m.name}</div>
      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--ink-2)' }}>{m.brand}</div>
      <div className="kicker" style={{ marginTop: 8 }}>SKU · {m.sku}</div>
      <hr className="hr" style={{ margin: '12px 0' }} />
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div className="num" style={{ fontSize: 22, fontWeight: 500 }}>
          <span className="rupee-pre">₹</span>{formatINR(m.rate)}
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>per {m.unit}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8, fontSize: 11, color: 'var(--ink-3)' }}>
        {m.lead_time_days > 0 && <span>· {m.lead_time_days}d lead</span>}
        {m.warranty && <span>· {m.warranty} warranty</span>}
      </div>
    </div>
  );
}
