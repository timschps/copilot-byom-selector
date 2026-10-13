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


def get_active() -> str | None:
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


def resolve(model: str | None) -> str | None:
    """Map the virtual alias to the currently selected backend; leave other names untouched."""
    if model == ACTIVE_ALIAS:
        return get_active() or model
    return model
