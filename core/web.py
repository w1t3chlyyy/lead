"""Адаптер: async-функция -> обработчик Vercel (BaseHTTPRequestHandler)."""
from __future__ import annotations

import asyncio
import json
import traceback
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlparse


@dataclass
class Req:
    method: str
    path: str
    query: dict
    headers: dict
    body: bytes = b""
    extra: dict = field(default_factory=dict)

    def json(self) -> dict:
        try:
            return json.loads(self.body or b"{}")
        except Exception:
            return {}


JSON = "application/json"


def make_handler(fn):
    class handler(BaseHTTPRequestHandler):
        def _do(self):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            u = urlparse(self.path)
            req = Req(self.command, u.path, dict(parse_qsl(u.query)),
                      {k.lower(): v for k, v in self.headers.items()}, body)
            try:
                status, payload, ctype = asyncio.run(fn(req))
            except Exception as e:
                traceback.print_exc()
                status, payload, ctype = 500, {"error": str(e)[:200]}, JSON
            if isinstance(payload, bytes):
                data = payload
            elif isinstance(payload, str):
                data = payload.encode()
            else:
                data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _do

        def log_message(self, *a):
            pass

    return handler
