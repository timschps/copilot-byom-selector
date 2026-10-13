"""Local usage tracking: Copilot sessions and per-request token/cost records (SQLite)."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid

from .config import home

# Approximate USD per 1M tokens (input, output). Estimates only, not the Azure invoice.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-1-mini": (0.40, 1.60),
    "gpt-4-1": (2.00, 8.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "claude-haiku": (1.00, 5.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-opus": (15.00, 75.00),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, pid INTEGER, started REAL, ended REAL, cwd TEXT);
CREATE TABLE IF NOT EXISTS requests (
  ts REAL, session TEXT, alias TEXT, prompt_tokens INTEGER, completion_tokens INTEGER,
  cost REAL, duration_ms INTEGER, ok INTEGER);
"""


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(home() / "usage.db", timeout=10)
    con.executescript(_SCHEMA)
    return con


def estimate_cost(alias: str, prompt: int, completion: int) -> float:
    name = alias.lower()
    # Longest key first so "gpt-4-1-mini" wins over "gpt-4-1".
    for key in sorted(PRICES, key=len, reverse=True):
        if key in name:
            pin, pout = PRICES[key]
            return (prompt * pin + completion * pout) / 1_000_000
    return 0.0


def start_session(cwd: str) -> str:
    sid = uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)", (sid, os.getpid(), time.time(), None, cwd)
        )
    return sid


def end_session(sid: str) -> None:
    with _db() as con:
        con.execute("UPDATE sessions SET ended=? WHERE id=?", (time.time(), sid))


def record(session, alias, prompt, completion, cost, duration_ms, ok) -> None:
    with _db() as con:
        con.execute(
            "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), session, alias, prompt, completion, cost, duration_ms, int(ok)),
        )


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFO
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def overview() -> dict:
    """Sessions (open first) with their usage, plus totals per model."""
    since_today = time.time() - 86400
    with _db() as con:
        sessions = []
        for sid, pid, started, ended, cwd in con.execute(
            "SELECT id,pid,started,ended,cwd FROM sessions ORDER BY started DESC LIMIT 30"
        ):
            row = con.execute(
                "SELECT COUNT(*),COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0),"
                "COALESCE(SUM(cost),0) FROM requests WHERE session=?",
                (sid,),
            ).fetchone()
            sessions.append(
                {
                    "id": sid,
                    "cwd": cwd,
                    "started": started,
                    "open": ended is None and _alive(pid),
                    "requests": row[0],
                    "prompt_tokens": row[1],
                    "completion_tokens": row[2],
                    "cost": round(row[3], 4),
                }
            )
        models = [
            {
                "alias": a,
                "requests": n,
                "prompt_tokens": p,
                "completion_tokens": c,
                "cost": round(cost, 4),
            }
            for a, n, p, c, cost in con.execute(
                "SELECT alias,COUNT(*),SUM(prompt_tokens),SUM(completion_tokens),SUM(cost) "
                "FROM requests GROUP BY alias ORDER BY 5 DESC"
            )
        ]
        today = con.execute(
            "SELECT COALESCE(SUM(cost),0),COUNT(*) FROM requests WHERE ts>?", (since_today,)
        ).fetchone()
        total = con.execute("SELECT COALESCE(SUM(cost),0),COUNT(*) FROM requests").fetchone()
    return {
        "sessions": sessions,
        "models": models,
        "cost_24h": round(today[0], 4),
        "requests_24h": today[1],
        "cost_total": round(total[0], 4),
        "requests_total": total[1],
    }
