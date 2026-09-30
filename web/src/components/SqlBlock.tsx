import { Fragment } from "react";

const KEYWORDS = new Set(
  ("select from where join inner left right outer on and or not in is null as group by order having limit offset " +
    "distinct case when then else end with union all asc desc count sum avg min max cast real integer text like between " +
    "exists iif strftime substr round coalesce over partition").split(" "),
);

/** Tiny tokenizer-based highlighter: keywords, strings and numbers. Good enough for display. */
export function SqlBlock({ sql }: { sql: string }) {
  const parts = sql.split(/('(?:[^']|'')*'|`[^`]*`|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]+\b)/g);
  return (
    <pre className="sql-block" aria-label="Generated SQL">
      {parts.map((p, i) => {
        if (!p) return null;
        if (p.startsWith("'")) return <span key={i} className="str">{p}</span>;
        if (/^\d/.test(p)) return <span key={i} className="num">{p}</span>;
        if (KEYWORDS.has(p.toLowerCase())) return <span key={i} className="kw">{p.toUpperCase()}</span>;
        return <Fragment key={i}>{p}</Fragment>;
      })}
    </pre>
  );
}
