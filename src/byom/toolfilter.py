"""Keep the tool list under a backend's limit (Azure OpenAI allows at most 128 per request)."""

from __future__ import annotations

import fnmatch
import re

import yaml

from .config import home

DEFAULTS = {
    "max_tools": 128,
    # Built-in Copilot tools have no "-" namespace prefix, so they are always kept (see _core).
    "always_keep": ["byom-*"],
    "deny": [],
    "skip_models": ["claude"],  # backends without a tool limit
}


def load_config() -> dict:
    path = home() / "tools.yaml"
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return cfg


def _name(tool: dict) -> str:
    return (tool.get("function") or {}).get("name") or tool.get("name") or ""


def _text(tool: dict) -> str:
    fn = tool.get("function") or tool
    return f"{_name(tool)} {fn.get('description', '')}"


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return c or ""
    return ""


def _used_names(messages: list[dict]) -> set[str]:
    used = set()
    for m in messages or []:
        for call in m.get("tool_calls") or []:
            used.add((call.get("function") or {}).get("name", ""))
    return used


def _match(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _core(name: str, cfg: dict) -> bool:
    return "-" not in name or _match(name, cfg["always_keep"])


def filter_tools(
    tools: list[dict], messages: list[dict], cfg: dict | None = None
) -> tuple[list[dict], list[str]]:
    """Return (kept tools, dropped tool names). Order of kept tools is preserved."""
    cfg = cfg or load_config()
    limit = int(cfg["max_tools"])
    if len(tools) <= limit and not cfg["deny"]:
        return tools, []

    candidates = [t for t in tools if not _match(_name(t), cfg["deny"])]
    if len(candidates) <= limit:
        keep = candidates
    else:
        used = _used_names(messages)
        query = _words(_last_user_text(messages))

        # Core tools first, then tools already used in this conversation, then by relevance.
        def rank(t):
            n = _name(t)
            return (_core(n, cfg), n in used, len(query & _words(_text(t))))

        chosen = {id(t) for t in sorted(candidates, key=rank, reverse=True)[:limit]}
        keep = [t for t in candidates if id(t) in chosen]
    kept_ids = {id(t) for t in keep}
    return keep, [_name(t) for t in tools if id(t) not in kept_ids]
