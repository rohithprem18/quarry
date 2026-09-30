import json

from fastapi.testclient import TestClient

from quarry.app import app


def test_databases_and_schema(make_services):
    make_services("SELECT 1")
    c = TestClient(app)
    dbs = c.get("/api/databases").json()
    assert dbs[0]["id"] == "shop" and dbs[0]["tables"] == 2 and dbs[0]["rows"] == 7
    sch = c.get("/api/databases/shop/schema").json()
    assert [t["name"] for t in sch["tables"]] == ["customers", "orders"]
    assert c.get("/api/databases/nope/schema").status_code == 404


def test_ask_streams_ndjson(make_services):
    make_services("```sql\nSELECT country, COUNT(*) FROM customers GROUP BY country\n```")
    r = TestClient(app).post("/api/ask", json={"db_id": "shop", "question": "Customers per country?"})
    events = [json.loads(x) for x in r.text.splitlines()]
    assert events[0]["type"] == "link" and events[-1]["type"] == "result"
    assert events[-1]["chart"]["kind"] == "bar" and events[-1]["row_count"] == 3


def test_ask_rate_limited(make_services):
    make_services("SELECT 1", asks_per_hour=1)
    c = TestClient(app)
    body = {"db_id": "shop", "question": "How many orders?"}
    assert c.post("/api/ask", json=body).status_code == 200
    assert c.post("/api/ask", json=body).status_code == 429


def test_health(make_services):
    make_services("SELECT 1")
    h = TestClient(app).get("/api/health").json()
    assert h["status"] == "ok" and h["databases"] == 1
