"""Pick a sensible visualisation for a result set (the console renders it)."""

from __future__ import annotations

import re

_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$|^\d{6}$")


def _numeric(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def suggest(columns: list[str], rows: list[list]) -> dict:
    """Returns {"kind": "stat" | "bar" | "line" | "table", ...}."""
    if not rows or not columns:
        return {"kind": "table"}
    if len(rows) == 1 and len(columns) == 1:
        return {"kind": "stat", "label": columns[0]}
    if len(columns) == 2 and 2 <= len(rows) <= 40 and all(_numeric(r[1]) or r[1] is None for r in rows):
        first = [r[0] for r in rows]
        if all(isinstance(x, str) and _DATE.match(x) for x in first) or all(
            isinstance(x, int) and 1900 <= x <= 2100 for x in first
        ):
            return {"kind": "line", "x": columns[0], "y": columns[1]}
        if len({str(x) for x in first}) == len(first):
            return {"kind": "bar", "x": columns[0], "y": columns[1]}
    return {"kind": "table"}
