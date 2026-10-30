"""Точка входа Vercel (FastAPI). Маршруты: /api/bot, /api/scan, /api/stats, /api/digest, /api/setup и мини-апп на /."""
from __future__ import annotations

import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

from core.web import JSON, Req, encode
from routes import bot, digest, scan, setup, stats

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

INDEX = Path(__file__).parent / "public" / "index.html"


async def run(fn, request: Request) -> Response:
    req = Req(request.method, request.url.path, dict(request.query_params),
              {k.lower(): v for k, v in request.headers.items()}, await request.body())
    try:
        status, payload, ctype = await fn(req)
    except Exception as e:
        traceback.print_exc()
        status, payload, ctype = 500, {"error": str(e)[:200]}, JSON
    return Response(encode(payload), status_code=status, media_type=ctype,
                    headers={"Cache-Control": "no-store"})


@app.post("/api/bot")
async def _bot(request: Request):
    return await run(bot.main, request)


@app.api_route("/api/scan", methods=["GET", "POST"])
async def _scan(request: Request):
    return await run(scan.main, request)


@app.get("/api/stats")
async def _stats(request: Request):
    return await run(stats.main, request)


@app.api_route("/api/digest", methods=["GET", "POST"])
async def _digest(request: Request):
    return await run(digest.main, request)


@app.get("/api/setup")
async def _setup(request: Request):
    return await run(setup.main, request)


@app.get("/", response_class=HTMLResponse)
async def _index():
    return HTMLResponse(INDEX.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})
