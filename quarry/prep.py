"""Build Quarry's per-database metadata from the BIRD dev set.

    python -m quarry.prep --bird data/raw --out data/dbs [--demo-only] [--download]

For every database this writes data/dbs/<db_id>/:
  schema.json   tables, columns, types, keys, BIRD column descriptions, sample values, row counts
  values.sqlite FTS5 index of distinct short text values (for matching question literals to cells)
  <db_id>.sqlite  a copy of the database (demo databases only; the rest stay in the raw folder)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

DEMO_DBS = ["formula_1", "california_schools", "thrombosis_prediction", "toxicology", "student_club", "superhero"]
BIRD_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
MINI_DEV_URL = (
    "https://huggingface.co/datasets/birdsql/bird_mini_dev/resolve/main/data/mini_dev_sqlite-00000-of-00001.json"
)
MAX_DISTINCT_INDEXED = 50_000
MAX_VALUE_LEN = 60


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def descriptions(db_dir: Path) -> dict[str, dict[str, dict]]:
    """{table_lower: {column_lower: {description, value_description}}} from database_description/*.csv"""
    out: dict[str, dict[str, dict]] = {}
    d = db_dir / "database_description"
    if not d.exists():
        return out
    for f in d.glob("*.csv"):
        cols: dict[str, dict] = {}
        for row in csv.DictReader(io.StringIO(read_text(f))):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name = row.get("original_column_name", "")
            if not name:
                continue
            desc = row.get("column_description") or row.get("column_name") or ""
            expanded = row.get("column_name", "")
            if expanded and expanded.lower() != name.lower() and expanded.lower() not in desc.lower():
                desc = f"{expanded}: {desc}" if desc else expanded
            cols[name.lower()] = {
                "description": " ".join(desc.split())[:300],
                "values": " ".join(row.get("value_description", "").split())[:300],
            }
        out[f.stem.lower()] = cols
    return out


def build(db_id: str, meta: dict, raw_dir: Path, out_dir: Path, copy_db: bool) -> dict:
    src = raw_dir / "dev_databases" / db_id / f"{db_id}.sqlite"
    dst = out_dir / db_id
    dst.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", errors="replace")
    desc = descriptions(src.parent)

    tables = []
    for ti, tname in enumerate(meta["table_names_original"]):
        cols = []
        for ci, (tidx, cname) in enumerate(meta["column_names_original"]):
            if tidx != ti:
                continue
            d = desc.get(tname.lower(), {}).get(cname.lower(), {})
            try:
                samples = [
                    r[0]
                    for r in con.execute(
                        f"SELECT DISTINCT {q(cname)} FROM {q(tname)} WHERE {q(cname)} IS NOT NULL "
                        f"AND length(CAST({q(cname)} AS TEXT)) <= 40 LIMIT 3"
                    )
                ]
            except sqlite3.Error:
                samples = []
            cols.append(
                {
                    "name": cname,
                    "type": meta["column_types"][ci],
                    "pk": ci in _flat(meta["primary_keys"]),
                    "description": d.get("description", ""),
                    "values": d.get("values", ""),
                    "samples": [str(s) for s in samples],
                    "index": ci,
                }
            )
        rows = con.execute(f"SELECT COUNT(*) FROM {q(tname)}").fetchone()[0]
        tables.append({"name": tname, "rows": rows, "columns": cols})

    col_ref = {c["index"]: (t["name"], c["name"]) for t in tables for c in t["columns"]}
    fks = [
        {"from": list(col_ref[a]), "to": list(col_ref[b])}
        for a, b in meta["foreign_keys"]
        if a in col_ref and b in col_ref
    ]
    schema = {"db_id": db_id, "tables": tables, "foreign_keys": fks}
    (dst / "schema.json").write_text(json.dumps(schema, indent=1, ensure_ascii=False), encoding="utf-8")

    # value index: distinct short text values per column
    vpath = dst / "values.sqlite"
    vpath.unlink(missing_ok=True)
    vcon = sqlite3.connect(vpath)
    vcon.execute("CREATE VIRTUAL TABLE v USING fts5(tbl UNINDEXED, col UNINDEXED, val, tokenize='unicode61')")
    indexed = 0
    for t in tables:
        for c in t["columns"]:
            if c["type"] != "text" or (c["pk"] and c["name"].lower().endswith("id")):
                continue
            n = con.execute(f"SELECT COUNT(DISTINCT {q(c['name'])}) FROM {q(t['name'])}").fetchone()[0]
            if not n or n > MAX_DISTINCT_INDEXED:
                continue
            vals = con.execute(
                f"SELECT DISTINCT {q(c['name'])} FROM {q(t['name'])} WHERE {q(c['name'])} IS NOT NULL "
                f"AND length({q(c['name'])}) BETWEEN 2 AND {MAX_VALUE_LEN}"
            ).fetchall()
            vcon.executemany("INSERT INTO v VALUES (?, ?, ?)", [(t["name"], c["name"], v[0]) for v in vals])
            indexed += len(vals)
    vcon.commit()
    vcon.execute("INSERT INTO v(v) VALUES('optimize')")
    vcon.commit()
    vcon.execute("VACUUM")
    vcon.close()
    con.close()
    if copy_db:
        shutil.copy2(src, dst / f"{db_id}.sqlite")
    return {"db_id": db_id, "tables": len(tables), "values_indexed": indexed, "copied": copy_db}


def _flat(pks) -> set[int]:
    out: set[int] = set()
    for p in pks:
        out.update(p if isinstance(p, list) else [p])
    return out


def download(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    if not (raw / "dev_databases").exists():
        print("downloading BIRD dev (346 MB)...")
        zpath = raw / "dev.zip"
        urllib.request.urlretrieve(BIRD_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            for n in z.namelist():
                if n.endswith(("dev.json", "dev_tables.json")):
                    (raw / Path(n).name).write_bytes(z.read(n))
            inner = [n for n in z.namelist() if n.endswith("dev_databases.zip")][0]
            zipfile.ZipFile(io.BytesIO(z.read(inner))).extractall(raw)
        zpath.unlink()
    if not (raw / "mini_dev_sqlite.json").exists():
        urllib.request.urlretrieve(MINI_DEV_URL, raw / "mini_dev_sqlite.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bird", default="data/raw")
    ap.add_argument("--out", default="data/dbs")
    ap.add_argument("--demo-only", action="store_true")
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    raw, out = Path(args.bird), Path(args.out)
    if args.download:
        download(raw)
    metas = {m["db_id"]: m for m in json.loads((raw / "dev_tables.json").read_text(encoding="utf-8"))}
    ids = DEMO_DBS if args.demo_only else sorted(metas)
    for db_id in ids:
        info = build(db_id, metas[db_id], raw, out, copy_db=db_id in DEMO_DBS)
        print(json.dumps(info))


if __name__ == "__main__":
    main()
