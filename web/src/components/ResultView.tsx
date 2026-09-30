import { useState } from "react";
import type { Chart } from "../types";

type Cell = string | number | null;

function fmt(v: Cell): string {
  if (v == null) return "—";
  if (typeof v === "number" && Number.isInteger(v) && v >= 1800 && v <= 2200) return String(v); // years
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return String(v);
}

function Bars({ rows, line }: { rows: Cell[][]; line: boolean }) {
  const vals = rows.map((r) => (typeof r[1] === "number" ? r[1] : 0));
  const max = Math.max(...vals.map(Math.abs), 1e-9);
  if (line) {
    const W = 640, H = 200, P = 28;
    const pts = vals.map((v, i) => [P + (i * (W - 2 * P)) / Math.max(1, vals.length - 1), H - P - (v / max) * (H - 2 * P)]);
    return (
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 220 }} role="img" aria-label="Line chart of the result">
        <line x1={P} x2={W - P} y1={H - P} y2={H - P} stroke="var(--hairline)" />
        <polyline fill="none" stroke="var(--sunset)" strokeWidth="2" points={pts.map((p) => p.join(",")).join(" ")} />
        {pts.map(([x, y], i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="4" fill="var(--sunset)" stroke="var(--canvas-card)" strokeWidth="2">
              <title>{`${fmt(rows[i][0])}: ${fmt(rows[i][1])}`}</title>
            </circle>
            {(i === 0 || i === pts.length - 1 || pts.length <= 12) && (
              <>
                <text x={x} y={H - 8} textAnchor="middle" fill="var(--mute)" fontSize="11" fontFamily="var(--mono)">{fmt(rows[i][0])}</text>
                <text x={x} y={y - 10} textAnchor="middle" fill="var(--body)" fontSize="12" fontFamily="var(--sans)">{fmt(rows[i][1])}</text>
              </>
            )}
          </g>
        ))}
      </svg>
    );
  }
  return (
    <div className="bars" role="list" aria-label="Bar chart of the result">
      {rows.map((r, i) => (
        <div key={i} className="bar-row" role="listitem" title={`${fmt(r[0])}: ${fmt(r[1])}`}>
          <span className="label">{fmt(r[0])}</span>
          <span className="track"><span className="fill" style={{ display: "block", width: `${(Math.abs(vals[i]) / max) * 100}%` }} /></span>
          <span className="val">{fmt(r[1])}</span>
        </div>
      ))}
    </div>
  );
}

export function ResultView({ columns, rows, rowCount, truncated, chart }: {
  columns: string[]; rows: Cell[][]; rowCount: number; truncated: boolean; chart: Chart;
}) {
  const chartable = chart.kind === "bar" || chart.kind === "line";
  const [mode, setMode] = useState<"chart" | "table">(chartable ? "chart" : "table");

  if (chart.kind === "stat" && rows.length === 1) {
    return (
      <div className="stat">
        <div className="mono-label">{columns[0]}</div>
        <div className="v">{fmt(rows[0][0])}</div>
      </div>
    );
  }
  return (
    <>
      <div className="result-head">
        <span className="caption">
          {rowCount.toLocaleString("en-US")} row{rowCount === 1 ? "" : "s"}
          {truncated ? ` · showing first ${rows.length}` : ""}
        </span>
        {chartable && (
          <div className="view-toggle">
            <button className={`pill sm ${mode === "chart" ? "on" : ""}`} onClick={() => setMode("chart")}>Chart</button>
            <button className={`pill sm ${mode === "table" ? "on" : ""}`} onClick={() => setMode("table")}>Table</button>
          </div>
        )}
      </div>
      {rowCount === 0 ? (
        <p className="caption">The query ran and returned no rows.</p>
      ) : mode === "chart" && chartable ? (
        <Bars rows={rows} line={chart.kind === "line"} />
      ) : (
        <div className="table-wrap" style={{ maxHeight: 360 }}>
          <table>
            <thead><tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} style={{ cursor: "default" }}>
                  {r.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : undefined}>{fmt(v)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
