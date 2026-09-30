"""The Text-to-SQL agent.

    link schema -> generate SQL -> safety check -> execute -> repair (on error or
    empty result, up to N times) -> result + chart suggestion

`run()` yields events so the console can show each step as it happens and the
benchmark can record first-attempt vs final correctness from one run.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from quarry.catalog import Database
from quarry.charts import suggest
from quarry.executor import execute
from quarry.linking import link
from quarry.llm import LLM, LLMError
from quarry.sqlsafe import UnsafeSQL, extract_sql, validate

SYSTEM = """You translate questions into a single SQLite query.
Rules:
- Return exactly one read-only query (SELECT or WITH ... SELECT) in a ```sql block, and nothing else.
- Use only the tables and columns in the schema. Quote identifiers that contain spaces or symbols with backticks.
- Treat the hint as authoritative: it defines terms, formulas and how values are encoded.
- Compare text against the stored values listed under "Values mentioned"; match their exact spelling and case.
- Select only what the question asks for, in the order it asks, with no extra columns.
- For ratios and percentages, CAST the numerator AS REAL. Use ORDER BY ... LIMIT 1 for "the highest/lowest".
- Join tables through the listed join keys."""


def build_prompt(schema_text: str, question: str, evidence: str) -> list[dict]:
    user = f"Schema:\n{schema_text}\n\n"
    if evidence.strip():
        user += f"Hint: {evidence.strip()}\n\n"
    user += f"Question: {question.strip()}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


class Agent:
    def __init__(self, llm: LLM, max_repairs: int = 2, timeout_s: float = 8.0, max_rows: int = 500):
        self.llm, self.max_repairs, self.timeout_s, self.max_rows = llm, max_repairs, timeout_s, max_rows

    async def run(self, db: Database, question: str, evidence: str = "") -> AsyncIterator[dict]:
        t0 = time.perf_counter()
        t = time.perf_counter()
        linked = link(db, question, evidence)
        yield {
            "type": "link",
            "ms": round((time.perf_counter() - t) * 1000, 1),
            "tables": linked.tables,
            "columns": linked.columns,
            "values": [h.__dict__ for h in linked.values],
            "schema_tokens": len(linked.schema_text) // 4,
            "total_tables": len(db.schema["tables"]),
        }

        messages = build_prompt(linked.schema_text, question, evidence)
        attempts: list[dict] = []
        result = None
        sql = ""
        for attempt in range(1, self.max_repairs + 2):
            try:
                comp = await self.llm.chat(messages)
            except LLMError as e:
                yield {"type": "error", "message": str(e)}
                return
            sql = extract_sql(comp.text)
            yield {
                "type": "sql",
                "attempt": attempt,
                "sql": sql,
                "model": comp.model,
                "ms": round(comp.ms, 1),
                "cache": comp.cache,
            }
            problem = None
            try:
                validate(sql)
            except UnsafeSQL as e:
                problem = f"The query was rejected: {e}. Return one read-only SELECT query."
                result = None
                yield {"type": "exec", "attempt": attempt, "ok": False, "error": str(e), "rows": 0, "ms": 0}
            else:
                result = await asyncio.to_thread(execute, db.path, sql, self.timeout_s, self.max_rows)
                yield {
                    "type": "exec",
                    "attempt": attempt,
                    "ok": result.ok,
                    "error": result.error,
                    "rows": result.row_count,
                    "ms": round(result.ms, 1),
                }
                if not result.ok:
                    problem = f"SQLite returned an error: {result.error}. Return a corrected query."
                elif result.row_count == 0 and attempt == 1:
                    problem = (
                        "The query returned no rows. Check each filter against the stored values and the hint "
                        "(spelling, case, date formats) and return a corrected query. If an empty result is "
                        "genuinely correct, return the same query."
                    )
            attempts.append(
                {
                    "attempt": attempt,
                    "sql": sql,
                    "ok": bool(result and result.ok),
                    "rows": result.row_count if result else 0,
                    "model": comp.model,
                }
            )
            if problem is None or attempt == self.max_repairs + 1:
                break
            if attempt > 1 and attempts[-1]["sql"] == attempts[-2]["sql"]:
                break  # the model stands by its query
            yield {"type": "repair", "attempt": attempt, "reason": problem.split(".")[0]}
            messages = messages + [
                {"role": "assistant", "content": f"```sql\n{sql}\n```"},
                {"role": "user", "content": problem},
            ]

        if result is None or not result.ok:
            yield {
                "type": "error",
                "message": (result.error if result else "no valid query produced"),
                "sql": sql,
                "attempts": attempts,
            }
            return
        yield {
            "type": "result",
            "sql": sql,
            "columns": result.columns,
            "rows": result.rows[:200],
            "row_count": result.row_count,
            "truncated": result.truncated or result.row_count > 200,
            "chart": suggest(result.columns, result.rows),
            "attempts": attempts,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    async def answer(self, db: Database, question: str, evidence: str = "") -> dict:
        """Non-streaming convenience: returns every event plus the final one."""
        events = [e async for e in self.run(db, question, evidence)]
        return {"events": events, "final": events[-1]}
