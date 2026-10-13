"""Runtime model selection shared by the CLI, the gateway hook and the MCP server."""

from __future__ import annotations

import json

import yaml

from .config import home

ACTIVE_ALIAS = "byom-active"
_HIDDEN = ("dall-e",)  # image models cannot serve Copilot


def _state_path():
    return home() / "active.json"


def list_aliases() -> list[str]:
    cfg = home() / "litellm.config.yaml"
    if not cfg.exists():
        return []
    entries = (yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("model_list", [])
    return [e["model_name"] for e in entries if not any(h in e["model_name"] for h in _HIDDEN)]


def _sessions_path():
    return home() / "session-models.json"


def _session_map() -> dict:
    p = _sessions_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def get_session_model(session: str | None) -> str | None:
    """Model override for one Copilot session, or None to follow the global selection."""
    alias = _session_map().get(session) if session else None
    return alias if alias in list_aliases() else None


def set_session_model(session: str, alias: str | None) -> None:
    known = list_aliases()
    if alias is not None and alias not in known:
        raise ValueError(f"Unknown model '{alias}'. Available: {', '.join(known) or 'none'}")
    m = _session_map()
    if alias is None:
        m.pop(session, None)
    else:
        m[session] = alias
    _sessions_path().write_text(json.dumps(m), encoding="utf-8")


def get_active(session: str | None = None) -> str | None:
    if (own := get_session_model(session)) is not None:
        return own
    path = _state_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("alias")


def set_active(alias: str) -> None:
    known = list_aliases()
    if alias not in known:
        raise ValueError(f"Unknown model '{alias}'. Available: {', '.join(known) or 'none'}")
    _state_path().write_text(json.dumps({"alias": alias}), encoding="utf-8")


def ensure_active() -> str | None:
    """Keep the selection valid after `sync`: fall back to the first available alias."""
    aliases = list_aliases()
    current = get_active()
    if current in aliases:
        return current
    if aliases:
        set_active(aliases[0])
        return aliases[0]
    return None


def rename_prefix(old: str, new: str) -> None:
    """Keep the selection when a profile's alias prefix changes."""
    current = get_active()
    if current and current.startswith(old + "-"):
        _state_path().write_text(json.dumps({"alias": new + current[len(old) :]}), encoding="utf-8")


def resolve(model: str | None, session: str | None = None) -> str | None:
    """Map the virtual alias, and model names Copilot picks by itself, to the active backend."""
    if model and model != ACTIVE_ALIAS and model in list_aliases():
        return model
    return (get_active(session) or model) if model else model
