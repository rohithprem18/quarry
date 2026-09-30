import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ResultView } from "../components/ResultView";
import { SqlBlock } from "../components/SqlBlock";
import { fmtMs } from "../format";
import type { AgentEvent, DatabaseInfo, Health } from "../types";

type Step = Exclude<AgentEvent, { type: "result" }>;
type Result = Extract<AgentEvent, { type: "result" }>;

function describe(e: Step): { title: string; detail?: string; ms?: number; tone?: "fail" | "hit" } {
  switch (e.type) {
    case "link":
      return {
        title: `Linked ${e.tables.length} of ${e.total_tables} tables`,
        detail: e.tables.join(", ") + (e.values.length ? ` · matched ${[...new Map(e.values.map((v) => [v.value.toLowerCase(), v.value])).values()].map((v) => `“${v}”`).join(", ")}` : "") +
          ` · ${e.schema_tokens.toLocaleString()} schema tokens`,
        ms: e.ms,
      };
    case "sql":
      return { title: e.attempt === 1 ? "Wrote SQL" : `Rewrote SQL (attempt ${e.attempt})`, detail: `${e.model}${e.cache ? " · from cache" : ""}`, ms: e.ms };
    case "exec":
      return e.ok
        ? { title: `Ran on SQLite: ${e.rows.toLocaleString()} row${e.rows === 1 ? "" : "s"}`, ms: e.ms }
        : { title: "Query failed", detail: e.error ?? undefined, ms: e.ms, tone: "fail" };
    case "repair":
      return { title: "Self-correcting", detail: e.reason, tone: "hit" };
    case "error":
      return { title: "Could not answer", detail: e.message, tone: "fail" };
  }
}

export function Ask({ dbs, dbId, onDb, health }: { dbs: DatabaseInfo[] | null; dbId: string | null; onDb: (id: string) => void; health: Health | null }) {
  const db = dbs?.find((d) => d.id === dbId) ?? dbs?.[0] ?? null;
  const [question, setQuestion] = useState("");
  const [evidence, setEvidence] = useState("");
  const [showHint, setShowHint] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shownAttempt, setShownAttempt] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => { setSteps([]); setResult(null); setAsked(null); }, [db?.id]);

  const run = async (q: string, ev: string) => {
    if (!db || !q.trim() || busy) return;
    abort.current?.abort();
    const c = new AbortController();
    abort.current = c;
    setBusy(true); setSteps([]); setResult(null); setShownAttempt(null); setAsked(q.trim());
    try {
      await api.ask({ db_id: db.id, question: q.trim(), evidence: ev.trim() }, (e) => {
        if (e.type === "result") setResult(e);
        else setSteps((s) => [...s, e]);
      }, c.signal);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) setSteps((s) => [...s, { type: "error", message: "Connection lost." }]);
    } finally {
      setBusy(false);
    }
  };

  const sqls = steps.filter((s): s is Extract<Step, { type: "sql" }> => s.type === "sql");
  const current = shownAttempt ? sqls.find((s) => s.attempt === shownAttempt) : sqls[sqls.length - 1];

  return (
    <div className="view">
      <header className="view-head">
        <span className="eyebrow">Ask</span>
        <div className="row">
          <h1 className="display">Ask a database in plain English.</h1>
          <span className="caption">Real BIRD benchmark databases · {health?.limits.asks_per_hour ?? 20} questions per hour</span>
        </div>
      </header>

      <section className="ask">
        <div className="stack">
          <div className="card">
            <div className="mono-label" style={{ marginBottom: 10 }}>Database</div>
            <div className="db-list" role="radiogroup" aria-label="Database">
              {(dbs ?? []).map((d) => (
                <button key={d.id} role="radio" aria-checked={db?.id === d.id} className={`pill sm ${db?.id === d.id ? "on" : ""}`}
                        onClick={() => onDb(d.id)}>
                  {d.title}
                </button>
              ))}
            </div>
            {db && (
              <>
                <p className="caption" style={{ marginTop: 12 }}>{db.summary}</p>
                <div className="db-meta">
                  <span>{db.tables} tables</span><span>{db.columns} columns</span><span>{db.rows.toLocaleString()} rows</span>
                  <a className="caption" href={`#/schema?db=${db.id}`}>Browse schema →</a>
                </div>
              </>
            )}
          </div>

          <form className="card field" onSubmit={(e) => { e.preventDefault(); run(question, evidence); }}>
            <label htmlFor="q" className="mono-label">Question</label>
            <textarea id="q" rows={3} value={question} maxLength={500} placeholder={db ? `Ask about ${db.title.toLowerCase()}…` : "Ask…"}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(question, evidence); } }} />
            {showHint ? (
              <>
                <label htmlFor="hint" className="mono-label">Hint (optional)</label>
                <textarea id="hint" rows={2} value={evidence} maxLength={800} placeholder="Define terms, e.g. “eligible = FRPM Count / Enrollment”"
                          onChange={(e) => setEvidence(e.target.value)} />
              </>
            ) : (
              <button type="button" className="hint-toggle" onClick={() => setShowHint(true)}>+ Add a hint that defines a term or formula</button>
            )}
            <div className="composer-row">
              <span className="caption">The agent writes SQL, runs it read-only, and fixes its own errors.</span>
              <div className="pill-group">
                <button type="submit" className="pill primary" disabled={busy || !question.trim() || !db}>{busy ? "Running…" : "Run"}</button>
              </div>
            </div>
          </form>

          {db && db.examples.length > 0 && (
            <div className="card">
              <div className="mono-label" style={{ marginBottom: 10 }}>Try a benchmark question</div>
              <div className="example-list">
                {db.examples.slice(0, 3).map((ex, i) => (
                  <button key={i} className="example" disabled={busy}
                          onClick={() => { setQuestion(ex.question); setEvidence(ex.evidence); setShowHint(!!ex.evidence); run(ex.question, ex.evidence); }}>
                    {ex.question}
                    <span className="d">{ex.difficulty}{ex.evidence ? " · with hint" : ""}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="card" aria-live="polite">
          {!asked ? (
            <div className="empty-chat" style={{ padding: "48px 0" }}>
              <div className="card-title">Pick a question to see the agent work</div>
              <p className="caption">
                It links your question to the relevant tables and stored values, writes SQLite, runs it read-only, and
                rewrites the query if SQLite reports an error or finds nothing.
              </p>
            </div>
          ) : (
            <>
              <div className="card-head">
                <span className="card-title">{asked}</span>
                {result && <span className="mono-label">{fmtMs(result.ms)}</span>}
              </div>
              <ol className="trace-list" style={{ maxHeight: "none", marginBottom: 12 }}>
                {steps.map((s, i) => {
                  const d = describe(s);
                  return (
                    <li key={i} className={`trace-item ${d.tone ?? ""}`}>
                      <span className="idx">{String(i + 1).padStart(2, "0")}</span>
                      <div>
                        <div className="title">{d.title}</div>
                        {d.detail && <div className="detail">{d.detail}</div>}
                      </div>
                      <span className="ms">{d.ms != null ? fmtMs(d.ms) : ""}</span>
                    </li>
                  );
                })}
                {busy && <li className="trace-item"><span className="idx">··</span><div className="title muted">Working…</div><span /></li>}
              </ol>
              {current && (
                <>
                  <div className="result-head" style={{ marginTop: 0 }}>
                    <span className="mono-label">SQL</span>
                    {sqls.length > 1 && (
                      <div className="attempt-tabs">
                        {sqls.map((s) => (
                          <button key={s.attempt} className={`pill sm ${current.attempt === s.attempt ? "on" : ""}`} onClick={() => setShownAttempt(s.attempt)}>
                            Attempt {s.attempt}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <SqlBlock sql={current.sql} />
                </>
              )}
              {result && (
                <ResultView columns={result.columns} rows={result.rows} rowCount={result.row_count} truncated={result.truncated} chart={result.chart} />
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
