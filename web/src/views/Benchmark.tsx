import { api } from "../api";
import { useLoad } from "../hooks";
import { fmtPct } from "../format";

const TITLES: Record<string, string> = {
  formula_1: "Formula 1", california_schools: "California schools", thrombosis_prediction: "Thrombosis prediction",
  toxicology: "Toxicology", student_club: "Student club", superhero: "Superheroes", card_games: "Card games",
  codebase_community: "Codebase community", debit_card_specializing: "Debit cards",
  european_football_2: "European football", financial: "Czech bank",
};

export function Benchmark() {
  const [b, error] = useLoad((s) => api.benchmark(s), []);

  return (
    <div className="view">
      <header className="view-head">
        <span className="eyebrow">Benchmark</span>
        <div className="row">
          <h1 className="display">Measured on BIRD, not claimed.</h1>
          <span className="caption">{b ? `${b.n} questions · ${b.benchmark}` : ""}</span>
        </div>
        <p className="lead">
          BIRD is a public Text-to-SQL benchmark of real, messy databases. A prediction only counts when its result set is
          identical to the gold query's result set, the official execution-accuracy metric.
        </p>
      </header>
      {error && <div className="error-banner">Benchmark results are not available yet.</div>}
      {b && (
        <>
          <section className="kpis">
            <div className="card kpi"><span className="mono-label">Execution accuracy</span><span className="kpi-value">{fmtPct(b.overall.final, 1)}</span><span className="caption">after self-correction</span></div>
            <div className="card kpi"><span className="mono-label">First attempt</span><span className="kpi-value">{fmtPct(b.overall.first_attempt, 1)}</span><span className="caption">before any repair</span></div>
            <div className="card kpi"><span className="mono-label">Fixed by repair</span><span className="kpi-value">{b.repaired}</span><span className="caption">{b.broken_by_repair} made worse</span></div>
            <div className="card kpi"><span className="mono-label">Schema linking</span><span className="kpi-value">{fmtPct(b.schema_linking_table_recall, 1)}</span><span className="caption">kept every table the answer needs</span></div>
            <div className="card kpi"><span className="mono-label">Median time</span><span className="kpi-value">{b.median_seconds}<span className="unit">s</span></span><span className="caption">{b.avg_attempts} attempts on average</span></div>
          </section>

          <section className="bench">
            <div className="card">
              <div className="card-head">
                <span className="card-title">By difficulty</span>
                <div className="legend">
                  <span><i style={{ background: "var(--series-upstream)" }} />First attempt</span>
                  <span><i style={{ background: "var(--series-cache)" }} />After repair</span>
                </div>
              </div>
              {(["simple", "moderate", "challenging"] as const).map((d) => {
                const r = b.by_difficulty[d];
                if (!r) return null;
                return (
                  <div key={d} className="diff-row">
                    <div><div style={{ textTransform: "capitalize" }}>{d}</div><div className="caption">{r.n} questions</div></div>
                    <div className="tracks">
                      <div className="t"><i style={{ width: `${r.first_attempt * 100}%`, background: "var(--series-upstream)" }} /></div>
                      <div className="t"><i style={{ width: `${r.final * 100}%`, background: "var(--series-cache)" }} /></div>
                    </div>
                    <div className="pct">{fmtPct(r.final, 1)}</div>
                  </div>
                );
              })}
              <p className="caption" style={{ marginTop: 8 }}>{b.metric}. LLM calls go through Sluice: {Object.entries(b.providers).map(([p, n]) => `${p} ${n}`).join(", ")}.</p>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Database</th><th className="num">Questions</th><th className="num">Accuracy</th></tr></thead>
                <tbody>
                  {Object.entries(b.by_database).sort((x, y) => y[1].final - x[1].final).map(([db, r]) => (
                    <tr key={db} style={{ cursor: "default" }}>
                      <td>{TITLES[db] ?? db}</td><td className="num">{r.n}</td><td className="num">{fmtPct(r.final, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
