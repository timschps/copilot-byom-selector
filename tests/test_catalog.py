from byom import foundry


def test_compatibility_rules():
    assert foundry.is_compatible("OpenAI", "gpt-4.1")
    assert foundry.is_compatible("OpenAI", "gpt-5")
    assert foundry.is_compatible("Anthropic", "claude-haiku-4-5")
    assert not foundry.is_compatible("OpenAI", "gpt-5.1-codex")  # Responses API only
    assert not foundry.is_compatible("OpenAI", "gpt-4o-realtime-preview")
    assert not foundry.is_compatible("Meta", "llama-3")  # route not verified
