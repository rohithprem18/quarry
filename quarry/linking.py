"""Schema linking: choose the tables, columns and literal values a question needs.

Big schemas do not fit a free-tier token budget (the largest BIRD database has
199 columns), and irrelevant columns make models guess. Linking scores every
column against the question and the evidence hint:
  - word overlap with the column name, its BIRD description and sample values
  - columns named in the evidence (e.g. "Currency = 'EUR'")
  - columns whose actual cell values appear in the question (via an FTS index)
then keeps the best tables, adds bridge tables so they can be joined, and
renders a compact schema with descriptions, examples and matched values.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from quarry.catalog import Database

STOP = set(
    """a an the of in on at to for from by with and or not no is are was were be been being what which who whom
whose when where why how many much do does did have has had that this these those it its as than then there their them
they per each all any list give show find tell me name names number count total please between during
among into over
under about above below more most less least only one two three same other such
via also both either whether""".split()
)

MAX_TABLES = 5
WIDE_TABLE = 24  # tables wider than this are trimmed to their best columns
KEEP_COLUMNS = 14


def words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]*|\d+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")):
        w = w.lower()
        if w in STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def q(name: str) -> str:
    return f"`{name}`" if re.search(r"[^A-Za-z0-9_]", name) or name.upper() in {"ORDER", "GROUP", "INDEX"} else name


@dataclass
class ValueHit:
    table: str
    column: str
    value: str


@dataclass
class Linked:
    tables: list[str]
    columns: dict[str, list[str]]
    values: list[ValueHit]
    schema_text: str
    scores: dict[str, float] = field(default_factory=dict)


def value_hits(db: Database, text: str, limit: int = 10) -> list[ValueHit]:
    """Cell values that literally occur in the question or evidence."""
    if not db.values_path.exists():
        return []
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    toks = sorted({w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-']*", text) if w.lower() not in STOP and len(w) > 1})
    if not toks:
        return []
    con = sqlite3.connect(f"file:{db.values_path.as_posix()}?mode=ro&immutable=1", uri=True)
    rows: list[tuple] = []
    try:
        # one lookup per word: a single OR query lets frequent words crowd out rare, decisive ones
        for t in toks[:30]:
            try:
                rows += con.execute(
                    "SELECT tbl, col, val FROM v WHERE v MATCH ? ORDER BY bm25(v) LIMIT 40",
                    ('"' + t.replace('"', "") + '"',),
                ).fetchall()
            except sqlite3.Error:
                continue
    finally:
        con.close()
    hits: list[ValueHit] = []
    seen = set()
    for tbl, col, val in rows:
        v = str(val).strip()
        vl = v.lower()
        if len(vl) < 2 or vl in STOP:
            continue
        # whole-value match: the cell's text must appear in the question as a phrase
        if not re.search(r"(?<![a-z0-9])" + re.escape(vl) + r"(?![a-z0-9])", low):
            continue
        key = (tbl, col, vl)
        if key in seen:
            continue
        seen.add(key)
        hits.append(ValueHit(tbl, col, v))
    hits.sort(key=lambda h: -len(h.value))
    return hits[:limit]


def link(db: Database, question: str, evidence: str = "") -> Linked:
    schema = db.schema
    text = f"{question} {evidence}"
    qwords = set(words(text))
    ev_low = (evidence or "").lower()
    hits = value_hits(db, text)
    hit_cols = {(h.table.lower(), h.column.lower()) for h in hits}

    col_score: dict[tuple[str, str], float] = {}
    table_score: dict[str, float] = {}
    for t in schema["tables"]:
        tname = t["name"]
        tw = set(words(tname))
        best = 0.0
        for c in t["columns"]:
            name_w = set(words(c["name"]))
            desc_w = set(words(c["description"])) - name_w
            s = 3.0 * len(qwords & name_w) + 1.0 * min(3, len(qwords & desc_w))
            s += 0.5 * min(2, len(qwords & set(words(" ".join(c["samples"])))))
            if c["name"].lower() in ev_low or f"{tname}.{c['name']}".lower() in ev_low:
                s += 6.0
            if (tname.lower(), c["name"].lower()) in hit_cols:
                s += 5.0
            col_score[(tname, c["name"])] = s
            best = max(best, s)
        table_score[tname] = best + 2.5 * len(qwords & tw) + (4.0 if tname.lower() in ev_low else 0.0)

    ranked = sorted(schema["tables"], key=lambda t: -table_score[t["name"]])
    small = sum(len(t["columns"]) for t in schema["tables"]) <= 40
    if small:
        chosen = [t["name"] for t in ranked]
    else:
        chosen = [t["name"] for t in ranked if table_score[t["name"]] > 0][:MAX_TABLES] or [ranked[0]["name"]]
        chosen = _add_bridges(chosen, schema)

    fks = schema["foreign_keys"]
    fk_cols = {(a.lower(), b.lower()) for fk in fks for a, b in (fk["from"], fk["to"])}
    columns: dict[str, list[str]] = {}
    for tname in chosen:
        t = db.table(tname)
        cols = t["columns"]
        if len(cols) > WIDE_TABLE:
            keep = sorted(cols, key=lambda c: -col_score[(tname, c["name"])])[:KEEP_COLUMNS]
            keep_names = {c["name"] for c in keep}
            keep_names |= {c["name"] for c in cols if c["pk"] or (tname.lower(), c["name"].lower()) in fk_cols}
            cols = [c for c in cols if c["name"] in keep_names]
        columns[tname] = [c["name"] for c in cols]

    text_out = render(db, chosen, columns, hits, col_score)
    return Linked(chosen, columns, hits, text_out, {t: round(table_score[t], 1) for t in chosen})


def _add_bridges(chosen: list[str], schema: dict) -> list[str]:
    """Add tables that connect two chosen tables that have no direct foreign key."""
    adj: dict[str, set[str]] = {}
    for fk in schema["foreign_keys"]:
        a, b = fk["from"][0], fk["to"][0]
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    out = list(chosen)
    for i, a in enumerate(chosen):
        for b in chosen[i + 1 :]:
            if b in adj.get(a, set()):
                continue
            bridge = next((m for m in adj.get(a, set()) if b in adj.get(m, set())), None)
            if bridge and bridge not in out:
                out.append(bridge)
    return out


def render(
    db: Database,
    tables: list[str],
    columns: dict[str, list[str]],
    hits: list[ValueHit],
    col_score: dict[tuple[str, str], float],
) -> str:
    lines = []
    for tname in tables:
        t = db.table(tname)
        lines.append(f"Table {q(tname)} ({t['rows']:,} rows)")
        for c in t["columns"]:
            if c["name"] not in columns[tname]:
                continue
            notes = []
            d = c["description"]
            if d and d.lower() != c["name"].lower():
                notes.append(d[:90])
            if c["values"] and col_score.get((tname, c["name"]), 0) > 0 and c["values"].lower() not in ("", "unuseful"):
                notes.append("values: " + c["values"][:140])
            if c["samples"]:
                notes.append("e.g. " + ", ".join(repr(s)[:30] for s in c["samples"][:3]))
            pk = " PRIMARY KEY" if c["pk"] else ""
            lines.append(f"  {q(c['name'])} {c['type'].upper()}{pk}" + (f"  -- {'; '.join(notes)}" if notes else ""))
        hidden = len(t["columns"]) - len(columns[tname])
        if hidden:
            lines.append(f"  -- {hidden} more columns omitted as irrelevant")
    keys = [fk for fk in db.schema["foreign_keys"] if fk["from"][0] in tables and fk["to"][0] in tables]
    if keys:
        lines.append(
            "Joins: "
            + "; ".join(f"{q(a[0])}.{q(a[1])} = {q(b[0])}.{q(b[1])}" for a, b in ((k["from"], k["to"]) for k in keys))
        )
    if hits:
        lines.append(
            "Values mentioned in the question, as stored: "
            + "; ".join(f"{q(h.table)}.{q(h.column)} = '{h.value}'" for h in hits)
        )
    return "\n".join(lines)
