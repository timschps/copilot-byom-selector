import yaml

from byom import state
from byom.config import Profile, load_profiles, save_profiles, valid_prefix


def test_label_defaults_to_name_and_prefix_overrides():
    p = Profile("priv", "t", "s", "rg", "acct")
    assert p.label == "priv"
    p.prefix = "personal"
    assert p.label == "personal"


def test_prefix_roundtrip_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("BYOM_HOME", str(tmp_path))
    save_profiles({"priv": Profile("priv", "t", "s", "rg", "acct", prefix="personal")})
    assert load_profiles()["priv"].label == "personal"
    assert valid_prefix("my-tenant1") and not valid_prefix("Bad Prefix") and not valid_prefix("")


def test_rename_prefix_keeps_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("BYOM_HOME", str(tmp_path))
    cfg = {"model_list": [{"model_name": "priv-a"}]}
    (tmp_path / "litellm.config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    state.set_active("priv-a")
    state.rename_prefix("priv", "personal")
    assert state.get_active() == "personal-a"
