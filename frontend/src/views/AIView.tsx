import { ReactNode, useState } from 'react';
import { useProjectStore } from '../store';
import { aiAsk, aiMissingBOQ, aiAnomalies, aiValueEngineering } from '../api/ai';
import { formatINR } from '../ui/format';
import type { AskResponse, MissingBOQResponse, AnomalyResponse, VEResponse } from '../types';

const SEED_QUESTIONS = [
  'What is the total project cost?',
  'Which trade has the highest cost?',
  'List all items grouped by trade',
  'Suggest cheaper alternatives',
  'How much will changing all partitions to glass cost?',
  'What is missing from this BOQ vs the layout?',
  'Where am I over-spending vs similar projects?',
  'Suggest two value-engineering moves that save the most without changing look.',
];

// ─── Diagnostic types ─────────────────────────────────────────────────────

interface Diagnostic {
  id: 'missing' | 'anoms' | 've';
  icon: string;
  kicker: string;
  title: string;
  run: (projectId: number) => Promise<any>;
  render: (data: any) => ReactNode;
}

const DIAGNOSTICS: Diagnostic[] = [
  {
    id: 'missing', icon: '🔍', kicker: 'Anomaly Check', title: 'What might be missing',
    run: (pid) => aiMissingBOQ(pid),
    render: (d: MissingBOQResponse) => (
      <ul style={listReset}>
        {d?.missing?.length === 0 && <li className="muted" style={liPadding}>Nothing missing.</li>}
        {d?.missing?.map((m, i) => (
          <li key={i} style={liBorder}>
            <div style={liTitle}>{m.trade} · <span className="num">{m.suggested_qty} {m.unit}</span></div>
            <div style={liReason}>{m.reason}</div>
          </li>
        ))}
      </ul>
    ),
  },
  {
    id: 'anoms', icon: '📊', kicker: 'VS Similar Projects', title: 'Pricing anomalies',
    run: (pid) => aiAnomalies(pid),
    render: (d: AnomalyResponse) => (
      <ul style={listReset}>
        {d?.anomalies?.length === 0 && <li className="muted" style={liPadding}>No anomalies detected.</li>}
        {d?.anomalies?.map((a, i) => (
          <li key={i} style={liBorder}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={liTitle}>{a.trade}</span>
              <span style={sevBadge(a.severity)}>{a.severity}</span>
            </div>
            <div style={liReason}>{a.line}</div>
            <div className="num" style={{ fontSize: 12, marginTop: 2 }}>
              expected <span style={{ color: 'var(--ink-3)' }}>{a.expected}</span> · got <strong>{a.got}</strong>
            </div>
          </li>
        ))}
      </ul>
    ),
  },
  {
    id: 've', icon: '💰', kicker: 'Value Engineering', title: 'Save here, change nothing',
    run: (pid) => aiValueEngineering(pid),
    render: (d: VEResponse) => (
      <>
        {d?.suggestions?.length === 0 && <div className="muted" style={liPadding}>No VE suggestions.</div>}
        {d?.suggestions?.map((s, i) => (
          <div key={i} style={liBorder}>
            <div style={liTitle}>{s.trade}</div>
            <div style={liReason}>{s.change}</div>
            <div className="num" style={{ fontSize: 12, marginTop: 2, color: 'var(--leaf)' }}>
              save <span className="rupee-pre">₹</span>{formatINR(s.saving, { round: true })}
            </div>
          </div>
        ))}
        {d?.total_saving != null && d.total_saving > 0 && (
          <div style={{ paddingTop: 10, fontWeight: 600 }}>
            <div className="kicker">Total saving</div>
            <div className="num" style={{ fontSize: 22 }}>
              <span className="rupee-pre">₹</span>{formatINR(d.total_saving, { round: true })}
            </div>
          </div>
        )}
      </>
    ),
  },
];

// ─── Styles ───────────────────────────────────────────────────────────────

const listReset: React.CSSProperties = { margin: 0, padding: 0, listStyle: 'none' };
const liBorder: React.CSSProperties = { padding: '8px 0', borderBottom: '1px solid var(--rule)' };
const liTitle: React.CSSProperties = { fontSize: 13, fontWeight: 500 };
const liReason: React.CSSProperties = { fontSize: 12, color: 'var(--ink-3)', marginTop: 2 };
const liPadding: React.CSSProperties = { padding: 6 };

function sevBadge(s: 'low' | 'med' | 'high'): React.CSSProperties {
  const colour = s === 'high' ? 'var(--brick)' : s === 'med' ? 'var(--warm)' : 'var(--ink-2)';
  return {
    display: 'inline-block',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    padding: '2px 8px',
    borderRadius: 4,
    border: `1px solid ${colour}`,
    color: colour,
    background: 'transparent',
  };
}

// ─── Component ────────────────────────────────────────────────────────────

export default function AIView() {
  const project = useProjectStore((s) => s.currentProject);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [askPhase, setAskPhase] = useState<'idle' | 'asking'>('idle');
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown>>({});
  const [loadingDiag, setLoadingDiag] = useState<string | null>(null);

  async function ask(q?: string) {
    const text = (q ?? question).trim();
    if (!project || !text) return;
    setQuestion(text);
    setAskPhase('asking');
    try {
      setAnswer(await aiAsk(project.id, text));
    } catch (e: any) {
      setAnswer({
        answer: `Error: ${e?.message ?? e}. The AI feature requires MiMo v2.5 API access — confirm MIMO_API_KEY is configured in the backend.`,
        citations: [],
      });
    } finally {
      setAskPhase('idle');
    }
  }

  function handleSeedClick(q: string) {
    setQuestion(q);
    ask(q);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  }

  async function runDiagnostic(d: Diagnostic) {
    if (!project) return;
    setLoadingDiag(d.id);
    try {
      const data = await d.run(project.id);
      setDiagnostics((prev) => ({ ...prev, [d.id]: data }));
    } catch (e: any) {
      setDiagnostics((prev) => ({ ...prev, [d.id]: { error: e?.message ?? String(e) } }));
    } finally {
      setLoadingDiag(null);
    }
  }

  return (
    <div style={{ height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div style={{ textAlign: 'center', paddingTop: 40, paddingBottom: 8, flexShrink: 0 }}>
        <div className="kicker" style={{ marginBottom: 8 }}>AI copilot</div>
        <h2 className="display" style={{ fontSize: 36, fontWeight: 500, lineHeight: 1.05, margin: 0 }}>
          ask the <em>estimate</em>
        </h2>
      </div>

      {/* ── Chat input (centered, full-width) ──────────────────────── */}
      <div style={{ maxWidth: 640, width: '100%', margin: '0 auto', padding: '20px 32px 0', flexShrink: 0 }}>
        <div className="paper" style={{ padding: 16, borderRadius: 12 }}>
          <textarea
            className="field"
            placeholder="What do you want to know about this estimate?"
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            style={{
              resize: 'none',
              fontFamily: 'var(--font-body)',
              width: '100%',
              boxSizing: 'border-box',
              border: 'none',
              background: 'transparent',
              outline: 'none',
              fontSize: 15,
              padding: '4px 0',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => ask()}
              disabled={askPhase === 'asking' || !question.trim()}
              style={{ borderRadius: 8, padding: '8px 20px' }}
            >
              {askPhase === 'asking' ? 'Thinking…' : 'Ask ⌘↵'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Suggestion chips (horizontal scroll) ──────────────────── */}
      <div style={{ flexShrink: 0, padding: '16px 32px 0' }}>
        <div
          style={{
            maxWidth: 640,
            margin: '0 auto',
            display: 'flex',
            gap: 8,
            overflowX: 'auto',
            paddingBottom: 4,
            scrollbarWidth: 'thin',
          }}
        >
          {SEED_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => handleSeedClick(q)}
              style={{
                flexShrink: 0,
                background: 'var(--paper)',
                color: 'var(--draft)',
                border: '1px solid var(--rule)',
                borderRadius: 20,
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 500,
                padding: '6px 14px',
                whiteSpace: 'nowrap',
                transition: 'background 0.15s, border-color 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--accent)';
                e.currentTarget.style.borderColor = 'var(--accent)';
                e.currentTarget.style.color = 'var(--paper)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--paper)';
                e.currentTarget.style.borderColor = 'var(--rule)';
                e.currentTarget.style.color = 'var(--draft)';
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* ── Answer area ───────────────────────────────────────────── */}
      <div style={{ maxWidth: 640, width: '100%', margin: '24px auto 0', padding: '0 32px', flex: 1 }}>
        {!answer ? (
          <div
            className="display"
            style={{
              fontSize: 18,
              fontStyle: 'italic',
              color: 'var(--ink-3)',
              textAlign: 'center',
              padding: '48px 0',
            }}
          >
            <em>ask something</em> above to get started.
          </div>
        ) : (
          <div className="paper" style={{ padding: 24, borderRadius: 12, animation: 'draw-in 0.3s ease' }}>
            {/* ── Answer text with whitespace preserved ── */}
            <div
              style={{
                fontSize: 15,
                lineHeight: 1.7,
                fontFamily: 'var(--font-display)',
                fontWeight: 400,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {answer.answer}
            </div>

            {/* ── Citations ── */}
            {answer.citations && answer.citations.length > 0 && (
              <div style={{ marginTop: 16, borderTop: '1px solid var(--rule)', paddingTop: 12 }}>
                <div className="kicker" style={{ marginBottom: 6 }}>Sources</div>
                {answer.citations.map((c, i) => (
                  <div key={i} style={{ fontSize: 12, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="num muted">#{i + 1}</span>
                    {c.trade && <span className="badge" style={{ fontSize: 11 }}>{c.trade}</span>}
                    {c.quote && <span style={{ color: 'var(--ink-2)' }}>{c.quote}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 3 Analysis cards at bottom ────────────────────────────── */}
      <div
        style={{
          maxWidth: 960,
          width: '100%',
          margin: '32px auto 32px',
          padding: '0 32px',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 16,
          flexShrink: 0,
        }}
      >
        {DIAGNOSTICS.map((d) => {
          const data = diagnostics[d.id] as Parameters<typeof d.render>[0] | undefined;
          const isError = data && 'error' in (data as any);
          return (
            <section key={d.id} className="paper" style={{ padding: 16, borderRadius: 12, display: 'flex', flexDirection: 'column' }}>
              {/* Card header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 20 }}>{d.icon}</span>
                  <div>
                    <div className="kicker" style={{ marginBottom: 0 }}>{d.kicker}</div>
                    <div style={{ fontSize: 15, fontWeight: 600, marginTop: 1 }}>{d.title}</div>
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  type="button"
                  onClick={() => runDiagnostic(d)}
                  disabled={loadingDiag === d.id}
                  style={{ padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, flexShrink: 0 }}
                >
                  {loadingDiag === d.id ? '…' : 'Run'}
                </button>
              </div>

              <hr className="hr" style={{ marginBottom: 12, marginTop: 0 }} />

              {/* Card body */}
              <div style={{ flex: 1, overflow: 'auto' }}>
                {isError ? (
                  <div style={{ fontSize: 12, color: 'var(--brick)', padding: 6 }}>
                    {(data as any).error}
                  </div>
                ) : data ? (
                  d.render(data)
                ) : (
                  <div className="muted" style={{ fontSize: 12, textAlign: 'center', padding: '16px 0' }}>
                    Click <strong>Run</strong> to populate.
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
