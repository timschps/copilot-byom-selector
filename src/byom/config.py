"""Profile storage. Lives in the user's home directory, never in the repo."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


def home() -> Path:
    path = Path(os.environ.get("BYOM_HOME", Path.home() / ".byom"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Profile:
    name: str
    tenant_id: str
    subscription_id: str
    resource_group: str
    account: str  # Foundry / Azure AI Services account name
    wire_api: str = "completions"  # or "responses" for GPT-5 family


def profiles_path() -> Path:
    return home() / "profiles.yaml"


def load_profiles() -> dict[str, Profile]:
    path = profiles_path()
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {n: Profile(name=n, **v) for n, v in raw.get("profiles", {}).items()}


def save_profiles(profiles: dict[str, Profile]) -> None:
    data = {}
    for name, p in profiles.items():
        d = asdict(p)
        d.pop("name")
        data[name] = d
    profiles_path().write_text(yaml.safe_dump({"profiles": data}, sort_keys=True), encoding="utf-8")


def get_profile(name: str) -> Profile:
    profiles = load_profiles()
    if name not in profiles:
        raise KeyError(f"Unknown profile '{name}'. Known: {', '.join(profiles) or 'none'}")
    return profiles[name]
