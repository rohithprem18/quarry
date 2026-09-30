"""Extract SQL from model output and allow only a single read-only query."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.*?)```", re.S | re.I)
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Merge,
    exp.TruncateTable,
)


class UnsafeSQL(ValueError):
    pass


def extract_sql(text: str) -> str:
    """Pull the query out of a fenced block, or take the text from the first SELECT/WITH."""
    m = _FENCE.findall(text or "")
    sql = m[-1] if m else text or ""
    if not m:
        start = re.search(r"\b(WITH|SELECT)\b", sql, re.I)
        sql = sql[start.start() :] if start else sql
    return sql.strip().rstrip(";").strip()


def validate(sql: str) -> str:
    """Raises UnsafeSQL unless `sql` is exactly one SELECT (or WITH ... SELECT) statement."""
    if not sql:
        raise UnsafeSQL("empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.SqlglotError as e:  # parse and tokenizer errors (e.g. prose instead of SQL)
        # sqlglot is stricter than SQLite in places; let SQLite report real syntax errors,
        # but still refuse anything that is not plainly a query.
        if not re.match(r"^\s*(WITH|SELECT)\b", sql, re.I) or ";" in sql:
            raise UnsafeSQL(f"could not parse query: {str(e).splitlines()[0][:160]}") from e
        return sql
    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise UnsafeSQL(f"only SELECT queries are allowed, got {stmt.key.upper()}")
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeSQL(f"{node.key.upper()} is not allowed")
    return sql
