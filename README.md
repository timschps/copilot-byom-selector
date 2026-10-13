# copilot-byom-selector

Use several Azure AI Foundry models (across several Azure tenants) with GitHub Copilot CLI's BYOK mode.

```
copilot --(openai, localhost:4000)--> LiteLLM gateway --> Foundry deployments (per tenant profile)
```

Copilot CLI only supports one BYOK provider at a time, so this tool runs a local
OpenAI-compatible gateway ([LiteLLM](https://docs.litellm.ai)) that exposes every
deployment as an alias `<profile>-<deployment>`, and picks the alias per Copilot session.

## Features

- Per-tenant **profiles**, each with an isolated Entra token cache (personal vs. work tenant, so costs land in the right subscription).
- **Model management** (list / deploy / delete) through Azure Resource Manager.
- `sync` generates the gateway config from live deployments.
- No secrets on disk: resource keys are fetched via ARM when the gateway starts and passed as environment variables. Profiles live in `~/.byom` (override with `BYOM_HOME`), never in the repo.

## Setup

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[gateway,dev]"   # the gateway extra pulls in LiteLLM

byom profile add priv --tenant-id <tenant> --subscription-id <sub> --resource-group <rg> --account <foundry-account>
byom login priv
byom deploy priv gpt41 --model gpt-4.1 --version 2025-04-14
byom list priv
byom sync
byom serve            # terminal 1
byom copilot priv-gpt41   # terminal 2
```

For GPT-5 family models add `--wire-api responses` to the profile.

## Troubleshooting

- **`No response was returned` and nothing in the gateway log**: Copilot never called the gateway. Aliases are not in
  Copilot's model catalog, so `byom copilot` passes explicit token limits. If your Copilot setup loads many MCP servers,
  skills or plugins, the static context can exceed a 128k model's budget. Use a larger-context deployment (for example
  `gpt-4.1`) or test with a clean profile: `$env:COPILOT_HOME = "$env:TEMP\copilot-clean"`.
- **`UnicodeEncodeError` when the gateway starts on Windows**: `byom serve` already forces `PYTHONUTF8=1`.
- **Sign-in**: `byom login` uses device code flow (no browser window needed); tokens are cached per profile.

## Requirements and status

- Your identity needs *Cognitive Services Contributor* (manage deployments and read keys) on the account.
- Models must support streaming and tool calling (128k+ context recommended).
- Status: early. Verified end to end: device-code login, listing, `sync`, `serve` and a Copilot CLI prompt answered by an Azure OpenAI deployment (`gpt-4o-mini`, chat completions) in a personal tenant. Still to verify: GPT-5 via the Responses API, non-OpenAI Foundry models (`azure_ai/`).

## Documentation

- [Architecture](docs/architecture.md)
- [Setting up Foundry (Bicep or CLI) and multiple tenants](docs/foundry-setup.md)
- [Contributing](CONTRIBUTING.md)
- Infrastructure as code: [`infra/main.bicep`](infra/main.bicep)

## Tests

```powershell
pytest
```
