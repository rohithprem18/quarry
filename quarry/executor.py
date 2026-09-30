"""Run a query against a read-only SQLite database with a time limit."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Result:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    ms: float = 0.0
    error: str | None = None


def _jsonable(v):
    if isinstance(v, bytes):
        return v.hex()[:64]
    if isinstance(v, float):
        return round(v, 6)
    return v


def execute(db_path: Path, sql: str, timeout_s: float = 8.0, max_rows: int = 500) -> Result:
    t0 = time.perf_counter()
    deadline = t0 + timeout_s
    try:
        # immutable=1: SQLite skips locking entirely (the files are read-only in deployment)
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro&immutable=1", uri=True, check_same_thread=False)
    except sqlite3.Error as e:
        return Result(False, error=f"cannot open database: {e}")
    con.text_factory = lambda b: b.decode("utf-8", errors="replace")
    con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10_000)
    try:
        con.execute("PRAGMA query_only = 1")
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        count = len(rows)
        truncated = count > max_rows
        rows = rows[:max_rows]
        if truncated:
            count += sum(1 for _ in cur)  # finish counting without keeping rows
        return Result(
            True,
            columns,
            [[_jsonable(v) for v in r] for r in rows],
            count,
            truncated,
            (time.perf_counter() - t0) * 1000,
        )
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "interrupted" in msg:
            msg = f"query exceeded the {timeout_s:g}s time limit"
        return Result(False, ms=(time.perf_counter() - t0) * 1000, error=msg)
    except sqlite3.Error as e:
        return Result(False, ms=(time.perf_counter() - t0) * 1000, error=str(e))
    finally:
        con.close()
