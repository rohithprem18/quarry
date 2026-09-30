"""Execution accuracy on BIRD Mini-Dev (SQLite).

    python bench/eval_bird.py --n 150            # stratified sample, resumable
    python bench/eval_bird.py --summarize        # rebuild the summary from the log

Scoring follows BIRD's official EX metric: a prediction is correct when the set of
rows it returns equals the set returned by the gold SQL. Each run records both the
first attempt and the final answer after self-correction, so the value of the
repair loop is measured on the same questions.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quarry.agent import Agent  # noqa: E402
from quarry.catalog import Catalog  # noqa: E402
from quarry.config import get_settings  # noqa: E402
from quarry.executor import execute  # noqa: E402
from quarry.linking import link  # noqa: E402
from quarry.llm import LLM  # noqa: E402

RESULTS = ROOT / "bench" / "results"


def stratified(rows: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["difficulty"]].append(r)
    out = []
    for _, items in sorted(by.items()):
        k = round(n * len(items) / len(rows))
        out += rng.sample(items, k)
    rng.shuffle(out)
    return out


def rowset(res) -> set[tuple]:
    return {tuple(r) for r in res.rows}


def gold_tables(db, sql: str) -> set[str]:
    return {
        t["name"]
        for t in db.schema["tables"]
        if re.search(r"(?<![A-Za-z0-9_])`?" + re.escape(t["name"]) + r"`?(?![A-Za-z0-9_])", sql, re.I)
    }


async def run(n: int, seed: int, log: Path) -> None:
    s = get_settings()
    cat = Catalog(s.data_dir, s.raw_dir)
    agent = Agent(
        LLM(s.llm_base_url, s.llm_api_key, s.llm_model), max_repairs=s.max_repairs, timeout_s=30, max_rows=100_000
    )
    rows = json.loads((s.raw_dir / "mini_dev_sqlite.json").read_text(encoding="utf-8"))
    sample = stratified(rows, n, seed)
    done = set()
    if log.exists():
        done = {json.loads(line)["question_id"] for line in log.read_text(encoding="utf-8").splitlines() if line}
    todo = [r for r in sample if r["question_id"] not in done]
    print(f"{len(sample)} sampled, {len(done)} already done, {len(todo)} to run", flush=True)
    for i, r in enumerate(todo, 1):
        db = cat.get(r["db_id"])
        t = time.perf_counter()
        out = await agent.answer(db, r["question"], r["evidence"])
        gold = await asyncio.to_thread(execute, db.path, r["SQL"], 60, 1_000_000)
        attempts = [e for e in out["events"] if e["type"] == "sql"]
        first_ok = final_ok = False
        if attempts and gold.ok:
            first = await asyncio.to_thread(execute, db.path, attempts[0]["sql"], 30, 1_000_000)
            first_ok = first.ok and rowset(first) == rowset(gold)
        final = out["final"]
        if final["type"] == "result" and gold.ok:
            pred = await asyncio.to_thread(execute, db.path, final["sql"], 30, 1_000_000)
            final_ok = pred.ok and rowset(pred) == rowset(gold)
        linked = link(db, r["question"], r["evidence"])
        rec = {
            "question_id": r["question_id"],
            "db_id": r["db_id"],
            "difficulty": r["difficulty"],
            "question": r["question"],
            "gold_sql": r["SQL"],
            "pred_sql": final.get("sql"),
            "first_sql": attempts[0]["sql"] if attempts else None,
            "first_ok": first_ok,
            "final_ok": final_ok,
            "attempts": len(attempts),
            "models": [a["model"] for a in attempts],
            "error": final.get("message") if final["type"] == "error" else None,
            "gold_ok": gold.ok,
            "tables_recalled": gold_tables(db, r["SQL"]) <= set(linked.tables),
            "seconds": round(time.perf_counter() - t, 1),
        }
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(
            f"[{i}/{len(todo)}] {r['difficulty']:11s} {'OK ' if final_ok else 'NO '} "
            f"attempts={len(attempts)} {rec['seconds']}s {r['db_id']}",
            flush=True,
        )
        await asyncio.sleep(2)


def summarize(log: Path) -> dict:
    recs = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    recs = [r for r in recs if r["gold_ok"]]

    def acc(items, key):
        return round(sum(r[key] for r in items) / len(items), 4) if items else None

    by_diff = {}
    for d in ("simple", "moderate", "challenging"):
        items = [r for r in recs if r["difficulty"] == d]
        by_diff[d] = {"n": len(items), "first_attempt": acc(items, "first_ok"), "final": acc(items, "final_ok")}
    by_db = {}
    for db in sorted({r["db_id"] for r in recs}):
        items = [r for r in recs if r["db_id"] == db]
        by_db[db] = {"n": len(items), "final": acc(items, "final_ok")}
    models = collections.Counter(m.split("/")[0] for r in recs for m in r["models"])
    summary = {
        "benchmark": "BIRD Mini-Dev (SQLite), stratified sample",
        "metric": "execution accuracy (EX): predicted result set == gold result set",
        "n": len(recs),
        "overall": {"first_attempt": acc(recs, "first_ok"), "final": acc(recs, "final_ok")},
        "by_difficulty": by_diff,
        "by_database": by_db,
        "schema_linking_table_recall": acc(recs, "tables_recalled"),
        "repaired": sum(1 for r in recs if r["final_ok"] and not r["first_ok"]),
        "broken_by_repair": sum(1 for r in recs if r["first_ok"] and not r["final_ok"]),
        "avg_attempts": round(sum(r["attempts"] for r in recs) / len(recs), 2) if recs else None,
        "median_seconds": sorted(r["seconds"] for r in recs)[len(recs) // 2] if recs else None,
        "providers": dict(models),
    }
    (RESULTS / "bird_minidev_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    log = RESULTS / f"bird_minidev_{args.n}_seed{args.seed}.jsonl"
    if not args.summarize:
        asyncio.run(run(args.n, args.seed, log))
    print(json.dumps(summarize(log), indent=2))


if __name__ == "__main__":
    main()
