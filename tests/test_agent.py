import pytest

from quarry.agent import Agent
from quarry.linking import link, words

from .conftest import ScriptedLLM


def test_words_drop_stopwords_and_fold_plurals():
    assert words("How many orders were shipped?") == ["order", "shipped"]


def test_link_finds_values_and_join(db):
    linked = link(db, "Total order amount for customers in United Kingdom")
    assert set(linked.tables) == {"customers", "orders"}
    assert any(h.value == "United Kingdom" and h.column == "country" for h in linked.values)
    assert "Joins: orders.customer_id = customers.id" in linked.schema_text
    assert "customers.country = 'United Kingdom'" in linked.schema_text


async def collect(agent, db, q):
    return [e async for e in agent.run(db, q)]


@pytest.mark.asyncio
async def test_happy_path(db):
    llm = ScriptedLLM("```sql\nSELECT SUM(amount) FROM orders WHERE status = 'shipped'\n```")
    events = await collect(Agent(llm), db, "Total shipped amount?")
    final = events[-1]
    assert [e["type"] for e in events] == ["link", "sql", "exec", "result"]
    assert final["rows"] == [[470.0]] and final["chart"]["kind"] == "stat"


@pytest.mark.asyncio
async def test_repairs_sql_error(db):
    llm = ScriptedLLM("SELECT total FROM orders", "SELECT SUM(amount) AS total FROM orders")
    events = await collect(Agent(llm), db, "Total amount?")
    assert [e["type"] for e in events] == ["link", "sql", "exec", "repair", "sql", "exec", "result"]
    assert "no such column" in llm.prompts[1][-1]["content"]
    assert events[-1]["attempts"][0]["ok"] is False and events[-1]["attempts"][1]["ok"] is True


@pytest.mark.asyncio
async def test_empty_result_gets_one_retry(db):
    llm = ScriptedLLM(
        "SELECT name FROM customers WHERE country = 'UK'", "SELECT name FROM customers WHERE country = 'United Kingdom'"
    )
    events = await collect(Agent(llm), db, "Customers in the UK?")
    assert events[-1]["type"] == "result" and events[-1]["rows"] == [["Ada"]]


@pytest.mark.asyncio
async def test_unsafe_sql_is_never_executed(db):
    llm = ScriptedLLM("DELETE FROM orders", "DELETE FROM orders", "DELETE FROM orders")
    events = await collect(Agent(llm, max_repairs=2), db, "Delete everything")
    assert events[-1]["type"] == "error"
    assert all(e["rows"] == 0 for e in events if e["type"] == "exec")


@pytest.mark.asyncio
async def test_stops_when_model_repeats_itself(db):
    llm = ScriptedLLM("SELECT name FROM customers WHERE country = 'Mars'")
    events = await collect(Agent(llm, max_repairs=3), db, "Customers on Mars?")
    assert sum(e["type"] == "sql" for e in events) == 2  # original + one retry, then it stood by the query
    assert events[-1]["type"] == "result" and events[-1]["row_count"] == 0
