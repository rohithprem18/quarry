"""HTTP surface.

GET  /api/databases               demo databases with example questions
GET  /api/databases/{id}/schema   tables, columns, descriptions, join keys
POST /api/ask                     NDJSON stream of the agent's steps and the result
GET  /api/benchmark               BIRD Mini-Dev results
GET  /api/health
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from quarry import __version__
from quarry.agent import Agent
from quarry.catalog import Catalog
from quarry.config import Settings, get_settings
from quarry.limits import Limiter
from quarry.llm import LLM

HERE = Path(__file__).resolve().parent
EXAMPLES = json.loads((HERE / "examples.json").read_text(encoding="utf-8"))
BENCHMARK = HERE / "benchmark.json"


class Services:
    def __init__(
        self, s: Settings, llm: LLM | None = None, catalog: Catalog | None = None, limiter: Limiter | None = None
    ):
        self.settings = s
        self.catalog = catalog or Catalog(s.data_dir, s.raw_dir)
        self.llm = llm or LLM(s.llm_base_url, s.llm_api_key, s.llm_model)
        self.agent = Agent(self.llm, s.max_repairs, s.query_timeout_s, s.max_rows)
        self.limiter = limiter or Limiter(s.redis_url, s.redis_token)


_svc: Services | None = None


def services() -> Services:
    global _svc
    if _svc is None:
        _svc = Services(get_settings())
    return _svc


def set_services(svc: Services | None) -> None:
    global _svc
    _svc = svc


app = FastAPI(title="Quarry", version=__version__, description="Text-to-SQL agent over the BIRD benchmark databases")


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message}}, status_code=status)


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


@app.get("/api/databases")
async def databases():
    out = []
    for db in services().catalog.all():
        tables = db.schema["tables"]
        out.append(
            {
                "id": db.db_id,
                "title": db.title,
                "summary": db.summary,
                "tables": len(tables),
                "columns": sum(len(t["columns"]) for t in tables),
                "rows": sum(t["rows"] for t in tables),
                "examples": EXAMPLES.get(db.db_id, []),
            }
        )
    order = list(EXAMPLES)
    out.sort(key=lambda d: order.index(d["id"]) if d["id"] in order else 99)
    return out


@app.get("/api/databases/{db_id}/schema")
async def schema(db_id: str):
    db = services().catalog.get(db_id)
    if not db or not db.available:
        return _error(404, f"unknown database '{db_id}'")
    return {
        "id": db.db_id,
        "title": db.title,
        "tables": [
            {
                "name": t["name"],
                "rows": t["rows"],
                "columns": [{k: c[k] for k in ("name", "type", "pk", "description", "samples")} for c in t["columns"]],
            }
            for t in db.schema["tables"]
        ],
        "foreign_keys": db.schema["foreign_keys"],
    }


class AskRequest(BaseModel):
    db_id: str
    question: str = Field(min_length=3, max_length=500)
    evidence: str = Field(default="", max_length=800)


@app.post("/api/ask")
async def ask(body: AskRequest, request: Request):
    svc = services()
    db = svc.catalog.get(body.db_id)
    if not db or not db.available:
        return _error(404, f"unknown database '{body.db_id}'")
    s = svc.settings
    ok, remaining, reset = await svc.limiter.hit(f"ip:{_ip(request)}", s.asks_per_hour, 3600)
    if not ok:
        return _error(429, f"the demo allows {s.asks_per_hour} questions per hour; try again in {reset // 60 + 1} min")
    ok, _, _ = await svc.limiter.hit("all", s.asks_per_day_total, 86400)
    if not ok:
        return _error(429, "the demo's daily budget is used up; it resets at 00:00 UTC")

    async def ndjson():
        async for ev in svc.agent.run(db, body.question, body.evidence):
            yield (json.dumps(ev, default=str) + "\n").encode()

    return StreamingResponse(
        ndjson(),
        media_type="application/x-ndjson",
        headers={"cache-control": "no-cache", "x-remaining-hour": str(remaining)},
    )


@app.get("/api/benchmark")
async def benchmark():
    if not BENCHMARK.exists():
        return _error(404, "benchmark results not generated yet")
    return json.loads(BENCHMARK.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    svc = services()
    base = svc.settings.llm_base_url
    return {
        "status": "ok",
        "version": __version__,
        "llm": {
            "endpoint": base.split("//")[-1].split("/")[0],
            "via_sluice": "sluice" in base,
            "model": svc.settings.llm_model,
        },
        "databases": len(svc.catalog.all()),
        "max_repairs": svc.settings.max_repairs,
        "limits": {"asks_per_hour": svc.settings.asks_per_hour},
    }


_static = Path(os.getenv("QUARRY_STATIC_DIR", HERE.parent / "web" / "dist"))
if (_static / "index.html").exists() and os.getenv("VERCEL") is None:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_static, html=True), name="console")
