"""Builds the LiteLLM config and the Copilot CLI environment. No secrets are written to disk."""

from __future__ import annotations

import re

import yaml

from .config import Profile, home

PORT = 4000
GATEWAY_KEY = "byom-local"  # only protects the localhost gateway, not a real credential


def env_name(profile: str) -> str:
    return "BYOM_KEY_" + re.sub(r"\W", "_", profile).upper()


def alias(profile: str, deployment: str) -> str:
    return f"{profile}-{deployment}"


def build_entries(profile: Profile, deployments, base: str) -> list[dict]:
    openai_base = base.replace(".cognitiveservices.azure.com", ".openai.azure.com")
    entries = []
    for d in deployments:
        fmt = (d.properties.model.format or "").lower()
        if fmt == "openai":
            params = {
                "model": f"azure/{d.name}",
                "api_base": openai_base,
                "api_key": f"os.environ/{env_name(profile.name)}",
                "api_version": "2025-04-01-preview",
            }
        elif fmt == "anthropic":
            # Claude on Foundry is served through the Anthropic Messages API.
            params = {
                "model": f"anthropic/{d.name}",
                "api_base": base.replace(".cognitiveservices.azure.com", ".services.ai.azure.com")
                + "/anthropic",
                "api_key": f"os.environ/{env_name(profile.name)}",
                # Copilot sends temperature and top_p; recent Claude models accept only one.
                "additional_drop_params": ["top_p"],
            }
        else:
            params = {
                "model": f"azure_ai/{d.name}",
                "api_base": openai_base.replace(".openai.azure.com", ".services.ai.azure.com")
                + "/models",
                "api_key": f"os.environ/{env_name(profile.name)}",
            }
        entries.append({"model_name": alias(profile.name, d.name), "litellm_params": params})
    return entries


def write_config(entries: list[dict]):
    path = home() / "litellm.config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "model_list": entries,
                "general_settings": {"master_key": GATEWAY_KEY},
                "litellm_settings": {
                    "drop_params": True,
                    "callbacks": ["byom.hook.proxy_handler_instance"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def copilot_env(
    model_alias: str,
    wire_api: str = "completions",
    max_prompt_tokens: int = 128000,
    max_output_tokens: int = 16000,
) -> dict[str, str]:
    # Aliases are not in Copilot's model catalog, so limits must be given explicitly.
    return {
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_PROVIDER_BASE_URL": f"http://127.0.0.1:{PORT}/v1",
        "COPILOT_PROVIDER_API_KEY": GATEWAY_KEY,
        "COPILOT_PROVIDER_WIRE_API": wire_api,
        "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": str(max_prompt_tokens),
        "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": str(max_output_tokens),
        "COPILOT_MODEL": model_alias,
    }
