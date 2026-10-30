"""Минимальный клиент PostgREST (Supabase) без лишних зависимостей."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .config import DEFAULTS, SUPABASE_KEY, SUPABASE_URL


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _h(prefer: str | None = None) -> dict:
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _out(r: httpx.Response, what: str) -> list:
    if r.status_code >= 300:
        raise RuntimeError(f"supabase {what}: {r.status_code} {r.text[:200]}")
    return r.json() if r.content else []


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


async def sel(http: httpx.AsyncClient, table: str, **params) -> list:
    return _out(await http.get(_url(table), params=params, headers=_h()), f"select {table}")


async def ins(http, table, rows, *, on_conflict=None, ignore=False, merge=False) -> list:
    prefer = ["return=representation"]
    if ignore:
        prefer.append("resolution=ignore-duplicates")
    if merge:
        prefer.append("resolution=merge-duplicates")
    params = {"on_conflict": on_conflict} if on_conflict else None
    r = await http.post(_url(table), json=rows, params=params, headers=_h(",".join(prefer)))
    return _out(r, f"insert {table}")


async def upd(http, table, data, **match) -> list:
    r = await http.patch(_url(table), json=data, params=match, headers=_h("return=representation"))
    return _out(r, f"update {table}")


async def dele(http, table, **match) -> list:
    r = await http.delete(_url(table), params=match, headers=_h("return=representation"))
    return _out(r, f"delete {table}")


# ---------- настройки ----------
async def get_settings(http) -> dict:
    cfg = dict(DEFAULTS)
    for row in await sel(http, "lb_settings", select="key,value"):
        cfg[row["key"]] = row["value"]
    return cfg


async def set_setting(http, key: str, value) -> None:
    await ins(http, "lb_settings", [{"key": key, "value": value}], on_conflict="key", merge=True)


# ---------- дедупликация ----------
async def claim(http, keys: list[str]) -> bool:
    """True, если все ключи новые (и мы их заняли)."""
    rows = await ins(http, "lb_seen", [{"key": k} for k in keys], on_conflict="key", ignore=True)
    return len(rows) == len(keys)


async def release(http, keys: list[str]) -> None:
    await dele(http, "lb_seen", key=f"in.({','.join(keys)})")


# ---------- замок на Telegram-сессию ----------
async def acquire_lock(http, secs: int) -> bool:
    rows = await upd(
        http, "lb_lock", {"locked_until": iso(now() + timedelta(seconds=secs))},
        id="eq.1", locked_until=f"lt.{iso(now())}",
    )
    return bool(rows)


async def release_lock(http) -> None:
    await upd(http, "lb_lock", {"locked_until": iso(now())}, id="eq.1")
