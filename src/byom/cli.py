from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time

import typer

from . import auth, foundry, gateway, state, usage
from .config import Profile, get_profile, home, load_profiles, save_profiles, valid_prefix

app = typer.Typer(
    help="Manage Foundry models and route GitHub Copilot CLI through a local gateway."
)
profile_app = typer.Typer(help="Manage tenant/resource profiles.")
app.add_typer(profile_app, name="profile")


@profile_app.command("add")
def profile_add(
    name: str,
    tenant_id: str = typer.Option(...),
    subscription_id: str = typer.Option(...),
    resource_group: str = typer.Option(...),
    account: str = typer.Option(..., help="Foundry / AI Services account name"),
    wire_api: str = typer.Option("completions", help="completions or responses"),
):
    profiles = load_profiles()
    profiles[name] = Profile(name, tenant_id, subscription_id, resource_group, account, wire_api)
    save_profiles(profiles)
    typer.echo(f"Saved profile '{name}' in {home()}")


@profile_app.command("list")
def profile_list():
    for p in load_profiles().values():
        typer.echo(
            f"{p.name}\tprefix={p.label}\ttenant={p.tenant_id}\t{p.account} ({p.resource_group})"
        )


@profile_app.command("set")
def profile_set(
    name: str,
    prefix: str = typer.Option(None, help="Prefix shown in model aliases, e.g. 'personal'"),
    wire_api: str = typer.Option(None, help="completions or responses"),
):
    """Change a profile's alias prefix or wire API, then refresh the gateway config."""
    profiles = load_profiles()
    if name not in profiles:
        typer.echo(f"Unknown profile '{name}'.")
        raise typer.Exit(1)
    old_label = profiles[name].label
    if prefix is not None:
        if not valid_prefix(prefix):
            typer.echo("Prefix: lowercase letters, digits and '-', max 25 characters.")
            raise typer.Exit(1)
        profiles[name].prefix = prefix
        state.rename_prefix(old_label, prefix)
    if wire_api:
        profiles[name].wire_api = wire_api
    save_profiles(profiles)
    sync()


@app.command()
def login(profile: str):
    """Sign in interactively to the profile's tenant (separate token cache per profile)."""
    typer.echo(f"Signed in as {auth.login(get_profile(profile))}")


@app.command("list")
def list_models(profile: str):
    for d in foundry.list_deployments(get_profile(profile)):
        m = d.properties.model
        typer.echo(f"{d.name}\t{m.format}/{m.name}@{m.version}\t{d.properties.provisioning_state}")


@app.command()
def deploy(
    profile: str,
    name: str = typer.Argument(..., help="Deployment name"),
    model: str = typer.Option(..., help="Model name, e.g. gpt-4.1"),
    version: str = typer.Option(...),
    fmt: str = typer.Option("OpenAI", "--format", help="Model format/publisher"),
    sku: str = typer.Option("GlobalStandard"),
    capacity: int = typer.Option(10),
    org_name: str = typer.Option(None, help="Anthropic models: organization name"),
    industry: str = typer.Option(None, help="Anthropic models: industry"),
    country: str = typer.Option(None, help="Anthropic models: ISO country code, e.g. BE"),
):
    provider_data = None
    if org_name or industry or country:
        if not (org_name and industry and country):
            typer.echo("--org-name, --industry and --country must be given together.")
            raise typer.Exit(1)
        provider_data = {
            "organizationName": org_name,
            "industry": industry,
            "countryCode": country,
        }
    foundry.deploy(get_profile(profile), name, model, version, fmt, sku, capacity, provider_data)
    typer.echo(f"Deployed {name}. Run 'byom sync' to refresh the gateway config.")


@app.command()
def delete(profile: str, name: str):
    foundry.delete(get_profile(profile), name)
    typer.echo(f"Deleted {name}. Run 'byom sync' to refresh the gateway config.")


@app.command()
def sync():
    """Rebuild the LiteLLM config from the live deployments of all profiles."""
    entries = []
    for p in load_profiles().values():
        entries += gateway.build_entries(p, foundry.list_deployments(p), foundry.endpoint(p))
    path = gateway.write_config(entries)
    typer.echo(f"{len(entries)} models written to {path}")
    for e in entries:
        typer.echo(f"  {e['model_name']}")
    active = state.ensure_active()
    typer.echo(f"Active model: {active or 'none'}")


@app.command()
def use(alias: str):
    """Switch the model behind 'byom-active' (takes effect on the next request)."""
    try:
        state.set_active(alias)
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1) from None
    typer.echo(f"Active model: {alias}")


@app.command()
def status():
    """List selectable models and mark the active one."""
    active = state.get_active()
    for a in state.list_aliases():
        typer.echo(f"{'*' if a == active else ' '} {a}")


@app.command()
def pick():
    """Choose the active model interactively (arrow keys)."""
    import questionary

    aliases = state.list_aliases()
    if not aliases:
        typer.echo("No models. Run 'byom sync' first.")
        raise typer.Exit(1)
    choice = questionary.select(
        "Active model", choices=aliases, default=state.get_active() or aliases[0]
    ).ask()
    if choice:
        state.set_active(choice)
        typer.echo(f"Active model: {choice}")


@app.command()
def ui(open_browser: bool = typer.Option(True, "--open/--no-open")):
    """Serve a local control page (http://127.0.0.1:4001) to view and switch the model."""
    import webbrowser

    from . import webui

    url = f"http://127.0.0.1:{webui.PORT}"
    typer.echo(f"Control page: {url} (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        webui.serve()
    except KeyboardInterrupt:
        pass


@app.command()
def mcp():
    """Run the MCP server (stdio) so Copilot can list and switch models."""
    from . import mcp_server

    mcp_server.main()


@app.command()
def serve():
    """Start the local LiteLLM gateway (fetches keys at start; nothing stored on disk)."""
    cmd, kwargs = _gateway_command()
    subprocess.run(cmd, check=False, **kwargs)


def _gateway_command() -> tuple[list[str], dict]:
    cfg = home() / "litellm.config.yaml"
    if importlib.util.find_spec("litellm") is None:
        typer.echo('LiteLLM is not installed. Run: pip install "copilot-byom-selector[gateway]"')
        raise typer.Exit(1)
    if not cfg.exists():
        typer.echo("Run 'byom sync' first.")
        raise typer.Exit(1)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"  # LiteLLM prints non-ASCII characters, which crash cp1252 consoles
    for p in load_profiles().values():
        env[gateway.env_name(p.name)] = foundry.get_key(p)
    cmd = [
        sys.executable,
        "-m",
        "litellm.proxy.proxy_cli",
        "--config",
        str(cfg),
        "--host",
        "127.0.0.1",
        "--port",
        str(gateway.PORT),
    ]
    return cmd, {"env": env}


def _gateway_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", gateway.PORT), timeout=1):
            return True
    except OSError:
        return False


def _start_gateway() -> subprocess.Popen:
    """Start the gateway hidden in the background; log to ~/.byom/gateway.log."""
    cmd, kwargs = _gateway_command()
    log = open(home() / "gateway.log", "ab")  # noqa: SIM115 - handle lives as long as the child
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags, **kwargs
    )
    typer.echo("Starting gateway...")
    for _ in range(90):
        if _gateway_up():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(1)
    proc.terminate()
    typer.echo(f"Gateway failed to start. See {home() / 'gateway.log'}")
    raise typer.Exit(1)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def copilot(
    ctx: typer.Context,
    model_alias: str = typer.Argument(
        state.ACTIVE_ALIAS, help="Model alias; default 'byom-active' is switchable in-session."
    ),
    lean: bool = typer.Option(
        False,
        "--lean",
        help="Use a separate, minimal Copilot home (no MCP servers/plugins) to stay under "
        "Azure OpenAI's 128-tool limit.",
    ),
    max_prompt_tokens: int = typer.Option(
        128000,
        "--max-prompt-tokens",
        help="Context budget Copilot assumes. Raise it (e.g. 400000) for large-context models "
        "when many MCP tools are loaded; keep it below the smallest model you will switch to.",
    ),
):
    """Launch Copilot CLI against the gateway with the given model alias (profile-deployment)."""
    exe = shutil.which("copilot")
    extra = list(ctx.args)
    if model_alias.startswith("-"):  # no alias given: this is already a Copilot option
        extra.insert(0, model_alias)
        model_alias = state.ACTIVE_ALIAS
    if not exe:
        typer.echo("copilot CLI not found on PATH")
        raise typer.Exit(1)
    wire = "completions"
    target = state.resolve(model_alias) or model_alias
    for p in load_profiles().values():
        if target.startswith(p.label + "-"):
            wire = p.wire_api
    env = {**os.environ, **gateway.copilot_env(model_alias, wire, max_prompt_tokens)}
    sid = usage.start_session(os.getcwd())
    env["COPILOT_PROVIDER_HEADERS"] = f"X-Byom-Session: {sid}"
    if lean:
        lean_home = home() / "copilot-lean"
        lean_home.mkdir(exist_ok=True)
        env["COPILOT_HOME"] = str(lean_home)
    started = None if _gateway_up() else _start_gateway()
    mcp_cfg = home() / f"mcp-{sid}.json"
    mcp_cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "byom": {
                        "type": "local",
                        "command": sys.executable,
                        "args": ["-m", "byom", "mcp"],
                        "env": {"BYOM_SESSION": sid},
                        "tools": ["*"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    try:
        code = subprocess.call([exe, "--additional-mcp-config", f"@{mcp_cfg}", *extra], env=env)
    finally:
        usage.end_session(sid)
        state.set_session_model(sid, None)
        mcp_cfg.unlink(missing_ok=True)
        if started:
            started.terminate()
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
