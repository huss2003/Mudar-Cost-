import { ReactNode, useEffect, useState } from 'react';
import { useProjectStore } from '../store';
import { aiAsk, aiMissingBOQ, aiAnomalies, aiValueEngineering, aiCapabilities } from '../api/ai';
import { formatINR } from '../ui/format';
import type { AskResponse, MissingBOQResponse, AnomalyResponse, VEResponse } from '../types';

const SEED_QUESTIONS = [
  'How much will changing all partitions to glass cost?',
  'Where am I over-spending vs similar projects?',
  'What is missing from this BOQ vs the layout?',
  'Suggest two value-engineering moves that save the most without changing look.',
];

interface Diagnostic {
  id: 'missing' | 'anoms' | 've';
  kicker: string;
  title: string;
  run: (projectId: number) => Promise<any>;
  render: (data: any) => ReactNode;
}

const DIAGNOSTICS: Diagnostic[] = [
  {
    id: 'missing', kicker: 'anomaly check', title: 'What might be missing',
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
    id: 'anoms', kicker: 'vs similar projects', title: 'Pricing anomalies',
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
    id: 've', kicker: 'value engineering', title: 'Save here, change nothing',
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
            <span className="kicker">Total saving</span>
            <div className="num" style={{ fontSize: 22 }}>
              <span className="rupee-pre">₹</span>{formatINR(d.total_saving, { round: true })}
            </div>
          </div>
        )}
      </>
    ),
  },
];

const listReset: React.CSSProperties = { margin: 0, padding: 0, listStyle: 'none' };
const liBorder: React.CSSProperties = { padding: '8px 0', borderBottom: '1px solid var(--rule)' };
const liTitle: React.CSSProperties = { fontSize: 13, fontWeight: 500 };
const liReason: React.CSSProperties = { fontSize: 12, color: 'var(--ink-3)', marginTop: 2 };
const liPadding: React.CSSProperties = { padding: 6 };

function sevBadge(s: 'low' | 'med' | 'high'): React.CSSProperties {
  const colour = s === 'high' ? 'var(--brick)' : s === 'med' ? 'var(--warm)' : 'var(--ink-2)';
  return { background: 'transparent', color: colour, borderColor: colour };
}

export default function AIView() {
  const project = useProjectStore((s) => s.currentProject);
  const [caps, setCaps] = useState<any[]>([]);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [askPhase, setAskPhase] = useState<'idle' | 'asking'>('idle');
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown>>({});
  const [loadingDiag, setLoadingDiag] = useState<string | null>(null);

  useEffect(() => {
    aiCapabilities().then((c: any) => setCaps(c?.capabilities ?? c ?? [])).catch(() => setCaps([]));
  }, []);

  async function ask() {
    if (!project || !question.trim()) return;
    setAskPhase('asking');
    try {
      setAnswer(await aiAsk(project.id, question.trim()));
    } catch (e: any) {
      setAnswer({ answer: `Error: ${e?.message ?? e}. The AI feature requires MiMo v2.5 API access — confirm MIMO_API_KEY is configured in the backend.`, citations: [] });
    } finally { setAskPhase('idle'); }
  }

  async function runDiagnostic(d: Diagnostic) {
    if (!project) return;
    setLoadingDiag(d.id);
    try {
      const data = await d.run(project.id);
      setDiagnostics((prev) => ({ ...prev, [d.id]: data }));
    } catch (e: any) {
      setDiagnostics((prev) => ({ ...prev, [d.id]: { error: e?.message ?? String(e) } }));
    } finally { setLoadingDiag(null); }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', height: '100%' }}>
      <aside style={{ borderRight: '1px solid var(--rule-strong)', padding: '32px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 12 }}>AI copilot</div>
        <h2 className="display" style={{ fontSize: 36, fontWeight: 500, lineHeight: 1.05 }}>ask the<br /><em>estimate</em>.</h2>
        <p style={{ marginTop: 12, color: 'var(--ink-2)', fontSize: 14, maxWidth: 420 }}>
          Powered by <em>MiMo v2.5</em> via OpenCode Go Premium.
          Every answer cites BOQ line IDs.
        </p>

        <hr className="hr" style={{ margin: '24px 0' }} />

        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>Ask</div>
          <textarea
            className="field"
            placeholder="What do you want to know about this estimate?"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            style={{ resize: 'vertical', fontFamily: 'var(--font-body)' }}
          />
          <button className="btn btn-primary" style={{ marginTop: 10, width: '100%', justifyContent: 'center' }}
            type="button" onClick={ask} disabled={askPhase === 'asking' || !question.trim()}>
            {askPhase === 'asking' ? 'Thinking…' : 'Run ⌘↵'}
          </button>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 16 }}>
            {SEED_QUESTIONS.map((q) => (
              <button key={q} className="badge draft" style={{
                background: 'var(--paper)', color: 'var(--draft)', borderColor: 'var(--draft)',
                cursor: 'pointer', fontSize: 11, padding: '4px 10px', textTransform: 'none',
                letterSpacing: 'normal', fontWeight: 500,
              }}
                type="button"
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--accent)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--paper)'; }}
                onClick={() => setQuestion(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>

        <hr className="hr" style={{ margin: '24px 0' }} />

        <div className="kicker" style={{ marginBottom: 8 }}>Capabilities</div>
        {caps.length === 0 ? (
          <div className="muted" style={{ fontSize: 12 }}>Loading capabilities from <code>/ai/capabilities</code>…</div>
        ) : (
          caps.map((c: any) => (
            <div key={c.endpoint} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--rule)' }}>
              <span className={`dot ${c.available ? 'dot-active' : 'dot-pending'}`} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 500 }}>{c.name}</div>
                <div className="kicker" style={{ color: 'var(--ink-3)', textTransform: 'none', letterSpacing: 0 }}>{c.description}</div>
              </div>
            </div>
          ))
        )}
      </aside>

      <div style={{ padding: '32px', overflow: 'auto' }}>
        <div className="draw-in">
          <section style={{ marginBottom: 32 }}>
            <div className="kicker" style={{ marginBottom: 8 }}>Answer</div>
            {!answer ? (
              <div className="display" style={{ fontSize: 28, fontStyle: 'italic', color: 'var(--ink-3)' }}><em>ask something</em> on the left.</div>
            ) : (
              <div className="paper" style={{ padding: 24 }}>
                <div style={{ fontSize: 16, lineHeight: 1.6, fontFamily: 'var(--font-display)', fontWeight: 400 }}>{answer.answer}</div>
                {answer.citations && answer.citations.length > 0 && (
                  <div style={{ marginTop: 16, borderTop: '1px solid var(--rule)', paddingTop: 12 }}>
                    <div className="kicker" style={{ marginBottom: 6 }}>Sources</div>
                    {answer.citations.map((c, i) => (
                      <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
                        <span className="num muted">#{i + 1}</span>
                        {c.trade && <span className="badge" style={{ marginRight: 6 }}>{c.trade}</span>}
                        {c.quote && <span style={{ color: 'var(--ink-2)' }}>{c.quote}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {DIAGNOSTICS.map((d) => {
              const data = diagnostics[d.id] as Parameters<typeof d.render>[0] | undefined;
              return (
                <section key={d.id} className="paper" style={{ padding: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
                    <div>
                      <div className="kicker">{d.kicker}</div>
                      <div className="display" style={{ fontSize: 22, fontWeight: 500, marginTop: 2 }}>{d.title}</div>
                    </div>
                    <button className="btn btn-secondary" type="button"
                      onClick={() => runDiagnostic(d)} disabled={loadingDiag === d.id}
                      style={{ padding: '6px 12px' }}>
                      {loadingDiag === d.id ? '…' : 'Run'}
                    </button>
                  </div>
                  <hr className="hr" style={{ marginBottom: 12 }} />
                  {data ? d.render(data) : <div className="muted" style={{ fontSize: 12 }}>Run to populate.</div>}
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
