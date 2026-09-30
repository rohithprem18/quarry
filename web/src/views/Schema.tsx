import { useEffect, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import type { DatabaseInfo } from "../types";

export function Schema({ dbs, dbId, onDb }: { dbs: DatabaseInfo[] | null; dbId: string | null; onDb: (id: string) => void }) {
  const id = dbId ?? dbs?.[0]?.id ?? null;
  const [schema, error] = useLoad((s) => (id ? api.schema(id, s) : Promise.resolve(null)), [id]);
  const [table, setTable] = useState<string | null>(null);
  useEffect(() => setTable(null), [id]);
  const current = schema?.tables.find((t) => t.name === table) ?? schema?.tables[0];
  const joins = schema?.foreign_keys.filter((k) => current && (k.from[0] === current.name || k.to[0] === current.name)) ?? [];

  return (
    <div className="view">
      <header className="view-head">
        <span className="eyebrow">Schema</span>
        <div className="row">
          <h1 className="display">{schema?.title ?? "Schema"}</h1>
          <div className="db-list">
            {(dbs ?? []).map((d) => (
              <button key={d.id} className={`pill sm ${id === d.id ? "on" : ""}`} onClick={() => onDb(d.id)}>{d.title}</button>
            ))}
          </div>
        </div>
      </header>
      {error && <div className="error-banner">Couldn't load this schema.</div>}

      <section className="schema">
        <div className="card">
          <div className="mono-label" style={{ marginBottom: 10 }}>{schema?.tables.length ?? 0} tables</div>
          <ul className="table-list">
            {schema?.tables.map((t) => (
              <li key={t.name}>
                <button className={current?.name === t.name ? "on" : undefined} onClick={() => setTable(t.name)}>
                  <span>{t.name}</span>
                  <span className="rows">{t.rows.toLocaleString()}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          {current && (
            <>
              <div className="card-head">
                <span className="card-title">{current.name}</span>
                <span className="mono-label">{current.columns.length} columns · {current.rows.toLocaleString()} rows</span>
              </div>
              {joins.length > 0 && (
                <p className="caption" style={{ marginBottom: 12 }}>
                  Joins: {joins.map((k) => `${k.from.join(".")} = ${k.to.join(".")}`).join(" · ")}
                </p>
              )}
              <div className="table-wrap cols">
                <table>
                  <thead><tr><th>Column</th><th>Type</th><th>Description</th><th>Examples</th></tr></thead>
                  <tbody>
                    {current.columns.map((c) => (
                      <tr key={c.name} style={{ cursor: "default" }}>
                        <td>{c.name}{c.pk && <span className="tag" style={{ marginLeft: 8 }}>key</span>}</td>
                        <td className="muted">{c.type}</td>
                        <td className="desc">{c.description && c.description !== c.name ? c.description : "—"}</td>
                        <td className="muted">{c.samples.slice(0, 2).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
