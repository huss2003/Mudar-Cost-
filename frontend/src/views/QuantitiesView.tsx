import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useProjectStore } from '../store';
import { computeQuantities, fetchBOQ, updateBoqItem } from '../api/boq';
import Empty from '../components/Empty';
import { formatINR } from '../ui/format';
import type { BOQLineItem } from '../types';

export default function QuantitiesView() {
  const project = useProjectStore((s) => s.currentProject);
  const [items, setItems] = useState<BOQLineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState<'idle' | 'computing'>('idle');
  const [filter, setFilter] = useState('');
  const [editingCell, setEditingCell] = useState<{ itemId: number; field: 'quantity' | 'rate' } | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

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

  /** Update a single field on a BOQ item, recalculate total, persist to backend */
  const handleFieldSave = useCallback(async (itemId: number, field: 'quantity' | 'rate', rawValue: string) => {
    setEditingCell(null);
    const numVal = parseFloat(rawValue);
    if (isNaN(numVal) || numVal < 0) return; // invalid — silently revert

    setItems((prev) => {
      const next = prev.map((it) => {
        if (it.id !== itemId) return it;
        const updated = { ...it, [field]: numVal };
        updated.total = Math.round((updated.quantity * updated.rate) * 100) / 100;
        return updated;
      });

      // Fire-and-forget persistence; optimistic update already applied
      const updatedItem = next.find((it) => it.id === itemId);
      if (updatedItem) {
        setSavingId(itemId);
        updateBoqItem(itemId, {
          quantity: updatedItem.quantity,
          rate: updatedItem.rate,
          total: updatedItem.total,
        }).catch((err) => {
          console.error('[QuantitiesView] PATCH failed', err);
          // Revert to server state on failure
          fetchBOQ(project!.id).then((r) => setItems(r.trades));
        }).finally(() => setSavingId(null));
      }
      return next;
    });
  }, [project?.id]);

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
                        <td className="num" style={{ textAlign: 'right' }}>
                          <EditableCell
                            itemId={it.id}
                            field="quantity"
                            value={it.quantity}
                            editingCell={editingCell}
                            setEditingCell={setEditingCell}
                            onSave={(val) => handleFieldSave(it.id, 'quantity', val)}
                            saving={savingId === it.id}
                            format={(v) => String(v)}
                          />
                        </td>
                        <td className="num" style={{ textAlign: 'right', color: 'var(--ink-2)' }}>
                          <EditableCell
                            itemId={it.id}
                            field="rate"
                            value={it.rate}
                            editingCell={editingCell}
                            setEditingCell={setEditingCell}
                            onSave={(val) => handleFieldSave(it.id, 'rate', val)}
                            saving={savingId === it.id}
                            prefix="₹"
                            format={(v) => formatINR(v)}
                            placeholder="—"
                          />
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

/* ── Inline-editable cell ─────────────────────────────────────────────────── */

interface EditableCellProps {
  itemId: number;
  field: 'quantity' | 'rate';
  value: number;
  editingCell: { itemId: number; field: 'quantity' | 'rate' } | null;
  setEditingCell: (c: { itemId: number; field: 'quantity' | 'rate' } | null) => void;
  onSave: (raw: string) => void;
  saving?: boolean;
  prefix?: string;
  format?: (v: number) => string;
  placeholder?: string;
}

function EditableCell({
  itemId, field, value, editingCell, setEditingCell, onSave, saving, prefix, format, placeholder,
}: EditableCellProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const isEditing = editingCell?.itemId === itemId && editingCell?.field === field;

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const display = format ? format(value) : String(value);

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="number"
        step="any"
        min="0"
        defaultValue={value}
        onBlur={(e) => onSave(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            (e.target as HTMLInputElement).blur(); // triggers onBlur → onSave
          }
          if (e.key === 'Escape') {
            setEditingCell(null);
          }
        }}
        style={{
          width: '100%',
          textAlign: 'right',
          padding: '2px 4px',
          border: '1px solid var(--ink)',
          borderRadius: 3,
          fontSize: 'inherit',
          fontFamily: 'inherit',
          background: 'var(--bg)',
          color: 'var(--ink)',
          outline: 'none',
          boxSizing: 'border-box',
        }}
      />
    );
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={() => setEditingCell({ itemId, field })}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') setEditingCell({ itemId, field });
      }}
      title="Click to edit"
      style={{
        cursor: 'pointer',
        borderBottom: '1px dashed var(--ink-3)',
        padding: '2px 0',
        display: 'inline-block',
        minWidth: 40,
        transition: 'border-color 0.15s, background 0.15s',
        borderRadius: 2,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(0,0,0,0.04)';
        e.currentTarget.style.borderBottomColor = 'var(--ink)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent';
        e.currentTarget.style.borderBottomColor = 'var(--ink-3)';
      }}
    >
      {saving ? (
        <span style={{ opacity: 0.5, fontSize: 11 }}>…</span>
      ) : (
        <>
          {prefix && <span style={{ color: 'var(--ink-4)' }}>{prefix}</span>}
          {value ? display : (placeholder ?? display)}
        </>
      )}
    </span>
  );
}

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {Array.from({ length: 6 }).map((_, i) => <div key={i} className="sk" style={{ height: 36 }} />)}
    </div>
  );
}
