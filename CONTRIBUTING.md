# Contributing

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check . ; ruff format --check . ; pytest
az bicep build --file infra/main.bicep --stdout > $null
```

- Keep `byom.gateway` free of Azure and network calls; add unit tests for new behaviour.
- Never commit secrets, profiles, or generated gateway configs (see `.gitignore`).
- CI runs lint, tests (Linux and Windows) and Bicep validation on every pull request.
- Release: push a `v*` tag; the release workflow builds and attaches the distribution.
