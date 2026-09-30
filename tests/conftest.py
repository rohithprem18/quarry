"""A tiny self-contained database (no BIRD download needed) and a scripted LLM."""

from __future__ import annotations

import json
import sqlite3

import pytest

from quarry.app import Services, set_services
from quarry.catalog import Catalog
from quarry.config import Settings
from quarry.limits import Limiter
from quarry.llm import Completion


def make_db(root):
    d = root / "shop"
    d.mkdir(parents=True)
    con = sqlite3.connect(d / "shop.sqlite")
    con.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, status TEXT);
        INSERT INTO customers VALUES (1, 'Ada', 'United Kingdom'), (2, 'Linus', 'Finland'), (3, 'Grace', 'United States');
        INSERT INTO orders VALUES (1, 1, 120.0, 'shipped'), (2, 1, 80.0, 'returned'), (3, 2, 50.0, 'shipped'),
                                  (4, 3, 300.0, 'shipped');
    """)
    con.commit()
    con.close()
    schema = {
        "db_id": "shop",
        "tables": [
            {
                "name": "customers",
                "rows": 3,
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "pk": True,
                        "description": "",
                        "values": "",
                        "samples": ["1", "2"],
                        "index": 1,
                    },
                    {
                        "name": "name",
                        "type": "text",
                        "pk": False,
                        "description": "customer name",
                        "values": "",
                        "samples": ["Ada"],
                        "index": 2,
                    },
                    {
                        "name": "country",
                        "type": "text",
                        "pk": False,
                        "description": "",
                        "values": "",
                        "samples": ["Finland"],
                        "index": 3,
                    },
                ],
            },
            {
                "name": "orders",
                "rows": 4,
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "pk": True,
                        "description": "",
                        "values": "",
                        "samples": ["1"],
                        "index": 4,
                    },
                    {
                        "name": "customer_id",
                        "type": "integer",
                        "pk": False,
                        "description": "",
                        "values": "",
                        "samples": ["1"],
                        "index": 5,
                    },
                    {
                        "name": "amount",
                        "type": "real",
                        "pk": False,
                        "description": "order value in USD",
                        "values": "",
                        "samples": ["120.0"],
                        "index": 6,
                    },
                    {
                        "name": "status",
                        "type": "text",
                        "pk": False,
                        "description": "",
                        "values": "shipped or returned",
                        "samples": ["shipped"],
                        "index": 7,
                    },
                ],
            },
        ],
        "foreign_keys": [{"from": ["orders", "customer_id"], "to": ["customers", "id"]}],
    }
    (d / "schema.json").write_text(json.dumps(schema))
    v = sqlite3.connect(d / "values.sqlite")
    v.execute("CREATE VIRTUAL TABLE v USING fts5(tbl UNINDEXED, col UNINDEXED, val)")
    v.executemany(
        "INSERT INTO v VALUES (?, ?, ?)",
        [
            ("customers", "country", "United Kingdom"),
            ("customers", "country", "Finland"),
            ("customers", "country", "United States"),
            ("customers", "name", "Ada"),
            ("customers", "name", "Linus"),
            ("customers", "name", "Grace"),
            ("orders", "status", "shipped"),
            ("orders", "status", "returned"),
        ],
    )
    v.commit()
    v.close()


class ScriptedLLM:
    """Returns the queued replies in order; records the prompts it saw."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[list[dict]] = []

    async def chat(self, messages, temperature=0.0, max_tokens=700):
        self.prompts.append(messages)
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text=text, model="fake/model", ms=5.0)

    async def aclose(self):
        pass


@pytest.fixture
def catalog(tmp_path):
    make_db(tmp_path)
    return Catalog(tmp_path, tmp_path / "raw")


@pytest.fixture
def db(catalog):
    return catalog.get("shop")


@pytest.fixture
def make_services(catalog):
    def build(*replies, asks_per_hour=20):
        s = Settings(
            llm_base_url="http://fake",
            llm_api_key="",
            llm_model="m",
            redis_url="",
            redis_token="",
            asks_per_hour=asks_per_hour,
        )
        svc = Services(s, llm=ScriptedLLM(*replies), catalog=catalog, limiter=Limiter())
        set_services(svc)
        return svc

    yield build
    set_services(None)
