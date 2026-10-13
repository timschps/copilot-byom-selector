from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys

import typer

from . import auth, foundry, gateway
from .config import Profile, get_profile, home, load_profiles, save_profiles

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
        typer.echo(f"{p.name}\ttenant={p.tenant_id}\t{p.account} ({p.resource_group})")


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
):
    foundry.deploy(get_profile(profile), name, model, version, fmt, sku, capacity)
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


@app.command()
def serve():
    """Start the local LiteLLM gateway (fetches keys at start; nothing stored on disk)."""
    cfg = home() / "litellm.config.yaml"
    if importlib.util.find_spec("litellm") is None:
        typer.echo('LiteLLM is not installed. Run: pip install "copilot-byom-selector[gateway]"')
        raise typer.Exit(1)
    if not cfg.exists():
        typer.echo("Run 'byom sync' first.")
        raise typer.Exit(1)
    env = os.environ.copy()
    for p in load_profiles().values():
        env[gateway.env_name(p.name)] = foundry.get_key(p)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "litellm.proxy.proxy_cli",
            "--config",
            str(cfg),
            "--host",
            "127.0.0.1",
            "--port",
            str(gateway.PORT),
        ],
        env=env,
        check=False,
    )


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def copilot(ctx: typer.Context, model_alias: str):
    """Launch Copilot CLI against the gateway with the given model alias (profile-deployment)."""
    exe = shutil.which("copilot")
    if not exe:
        typer.echo("copilot CLI not found on PATH")
        raise typer.Exit(1)
    wire = "completions"
    for name, p in load_profiles().items():
        if model_alias.startswith(name + "-"):
            wire = p.wire_api
    env = {**os.environ, **gateway.copilot_env(model_alias, wire)}
    raise typer.Exit(subprocess.call([exe, *ctx.args], env=env))


if __name__ == "__main__":
    app()
