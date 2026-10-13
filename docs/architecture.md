# Architecture

## Goal

GitHub Copilot CLI supports one BYOK provider per session. This project lets you use
many Azure AI Foundry models, across several Azure tenants, by placing a local
OpenAI-compatible gateway between Copilot CLI and Foundry.

```
                  +-------------------- byom CLI ----------------------+
                  |  profile / login / list / deploy / delete / sync    |
                  +----------+-------------------+----------------------+
                             | ARM (Entra, per-tenant token cache)
                             v
copilot CLI --> LiteLLM gateway (127.0.0.1:4000) --> Foundry account(s) in tenant A, B, ...
   (openai type,   alias -> deployment routing         (Azure OpenAI / Azure AI inference)
    model=alias)
```

## Components

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `byom.config` | Profile model and storage in `~/.byom` (or `BYOM_HOME`) | PyYAML |
| `byom.auth` | Interactive Entra sign-in, one isolated token cache per profile | azure-identity |
| `byom.foundry` | List, create and delete deployments; read account endpoint and keys (ARM) | azure-mgmt-cognitiveservices |
| `byom.gateway` | Pure functions that build the LiteLLM config and the Copilot environment | none |
| `byom.cli` | Thin Typer command layer, orchestration only | all of the above |
| `infra/main.bicep` | Declarative creation of the Foundry account and deployments | Azure |

Design rules:

- `gateway` has no I/O to Azure and is unit tested without mocks.
- All Azure access goes through `foundry`, so it is the only module to adapt when APIs change.
- Profiles are the unit of tenant isolation: tenant, subscription, resource group, account, token cache.

## Data and secrets

- Profiles contain identifiers only (no secrets) and live outside the repository.
- The generated `litellm.config.yaml` references keys as `os.environ/BYOM_KEY_<PROFILE>`.
- Keys are fetched through ARM (`listKeys`) when `byom serve` starts and are passed to the gateway
  process environment. They are never written to disk.
- The gateway binds to `127.0.0.1` and requires a static local key. This is not a credential for Azure.

## Request flow

1. `byom copilot <profile>-<deployment>` sets `COPILOT_PROVIDER_*` variables and starts `copilot`.
2. Copilot sends OpenAI-style requests to the gateway with `model=<alias>`.
3. LiteLLM looks up the alias and calls `azure/<deployment>` (OpenAI models), `anthropic/<deployment>` (Claude, via the Foundry Anthropic endpoint) or `azure_ai/<deployment>` (other Foundry models).

## Why these choices

- **Python**: LiteLLM and the Azure management SDKs are first-class in Python.
- **LiteLLM**: maintained, supports streaming and tool calling, many providers; avoids writing a proxy.
- **Bicep + CLI**: Bicep for the one-time, reviewable resource setup; the CLI for day-to-day model changes.
- **Keys over Entra tokens for inference**: simplest and works with LiteLLM today. Entra token support is a planned extension
  (set `disableLocalAuth` in Bicep once implemented).

## Known limitations

- Entra-token inference auth is not implemented yet.
- GPT-5 models need the Responses API (`wire_api: responses` in the profile); verify end to end against your deployment.
- Non-OpenAI, non-Anthropic Foundry models (`azure_ai/`) are untested.
- Anthropic deployments require provider data: `byom deploy ... --format Anthropic --org-name <n> --industry <i> --country <cc>`.
- On Windows ARM64 some LiteLLM dependencies (`tiktoken`, `fastuuid`) have no prebuilt wheels and need Rust plus the MSVC build tools; run the gateway elsewhere (WSL, container) or install those tools. `byom` management commands work without the `gateway` extra.
