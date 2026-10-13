from types import SimpleNamespace

from byom import gateway
from byom.config import Profile


def dep(name, fmt):
    return SimpleNamespace(name=name, properties=SimpleNamespace(model=SimpleNamespace(format=fmt)))


def test_entries_use_env_keys_and_prefixed_alias():
    p = Profile("priv", "t", "s", "rg", "acct")
    entries = gateway.build_entries(
        p,
        [dep("gpt5", "OpenAI"), dep("mistral", "Mistral AI"), dep("claude", "Anthropic")],
        "https://acct.cognitiveservices.azure.com",
    )
    assert [e["model_name"] for e in entries] == ["priv-gpt5", "priv-mistral", "priv-claude"]
    assert entries[2]["litellm_params"]["model"] == "anthropic/claude"
    assert entries[2]["litellm_params"]["api_base"] == (
        "https://acct.services.ai.azure.com/anthropic"
    )
    assert entries[0]["litellm_params"]["model"] == "azure/gpt5"
    assert entries[0]["litellm_params"]["api_base"] == "https://acct.openai.azure.com"
    assert entries[1]["litellm_params"]["model"] == "azure_ai/mistral"
    assert entries[0]["litellm_params"]["api_key"] == "os.environ/BYOM_KEY_PRIV"


def test_copilot_env_points_at_gateway():
    env = gateway.copilot_env("priv-gpt5", "responses")
    assert env["COPILOT_MODEL"] == "priv-gpt5"
    assert env["COPILOT_PROVIDER_WIRE_API"] == "responses"
    assert env["COPILOT_PROVIDER_BASE_URL"].endswith(":4000/v1")
