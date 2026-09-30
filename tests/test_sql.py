import pytest

from quarry.charts import suggest
from quarry.executor import execute
from quarry.sqlsafe import UnsafeSQL, extract_sql, validate


def test_extract_from_fence_and_bare_text():
    assert extract_sql("Here:\n```sql\nSELECT 1;\n```") == "SELECT 1"
    assert extract_sql("The answer is SELECT name FROM t") == "SELECT name FROM t"


@pytest.mark.parametrize(
    "sql", ["SELECT 1", "WITH x AS (SELECT 1 AS a) SELECT a FROM x", "SELECT a FROM t UNION SELECT b FROM u"]
)
def test_allows_queries(sql):
    assert validate(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "DROP TABLE orders",
        "SELECT 1; DROP TABLE orders",
        "PRAGMA table_info(orders)",
        "UPDATE orders SET amount = 0",
        "ATTACH 'x.db' AS x",
        "",
    ],
)
def test_rejects_everything_else(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql)


def test_executor_is_read_only(db):
    r = execute(db.path, "DELETE FROM orders")
    assert not r.ok and "readonly" in r.error.replace("-", "").lower()


def test_executor_times_out(db):
    r = execute(
        db.path, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c", timeout_s=0.3
    )
    assert not r.ok and "time limit" in r.error


def test_executor_truncates_but_counts(db):
    r = execute(db.path, "SELECT * FROM orders", max_rows=2)
    assert r.ok and len(r.rows) == 2 and r.row_count == 4 and r.truncated


def test_chart_suggestions():
    assert suggest(["n"], [[3]])["kind"] == "stat"
    assert suggest(["country", "total"], [["UK", 200.0], ["FI", 50.0]])["kind"] == "bar"
    assert suggest(["year", "races"], [[2019, 21], [2020, 17], [2021, 22]])["kind"] == "line"
    assert suggest(["a", "b", "c"], [[1, 2, 3]])["kind"] == "table"


def test_prose_is_rejected_not_crashing():
    with pytest.raises(UnsafeSQL):
        validate("I'm sorry, but I can't write that query because the schema, I cannot return it.")
