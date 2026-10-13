import json

import pytest
import yaml

from byom import state


@pytest.fixture
def byom_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BYOM_HOME", str(tmp_path))
    cfg = {"model_list": [{"model_name": "priv-a"}, {"model_name": "priv-b"}]}
    (tmp_path / "litellm.config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return tmp_path


def test_use_and_resolve(byom_home):
    state.set_active("priv-b")
    assert state.resolve(state.ACTIVE_ALIAS) == "priv-b"
    assert state.resolve("priv-a") == "priv-a"
    assert state.resolve("gpt-5.4-nano") == "priv-b"  # Copilot's own helper model names
    assert json.loads((byom_home / "active.json").read_text())["alias"] == "priv-b"


def test_unknown_alias_rejected(byom_home):
    with pytest.raises(ValueError):
        state.set_active("nope")


def test_ensure_active_falls_back(byom_home):
    state.set_active("priv-b")
    (byom_home / "litellm.config.yaml").write_text(
        yaml.safe_dump({"model_list": [{"model_name": "priv-a"}]}), encoding="utf-8"
    )
    assert state.ensure_active() == "priv-a"
