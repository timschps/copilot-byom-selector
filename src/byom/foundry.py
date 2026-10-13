"""Model management against an Azure AI Foundry (Cognitive Services AIServices) account."""

from __future__ import annotations

import requests
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import (
    Deployment,
    DeploymentModel,
    DeploymentProperties,
    Sku,
)

from .auth import ARM_SCOPE, credential
from .config import Profile


def client(profile: Profile) -> CognitiveServicesManagementClient:
    return CognitiveServicesManagementClient(credential(profile), profile.subscription_id)


def list_deployments(profile: Profile):
    return list(client(profile).deployments.list(profile.resource_group, profile.account))


def deploy(
    profile: Profile,
    name: str,
    model: str,
    version: str,
    fmt: str = "OpenAI",
    sku: str = "GlobalStandard",
    capacity: int = 10,
    provider_data: dict | None = None,
):
    if provider_data:
        return _deploy_rest(profile, name, model, version, fmt, sku, capacity, provider_data)
    properties = DeploymentProperties(
        model=DeploymentModel(format=fmt, name=model, version=version)
    )
    return (
        client(profile)
        .deployments.begin_create_or_update(
            profile.resource_group,
            profile.account,
            name,
            Deployment(properties=properties, sku=Sku(name=sku, capacity=capacity)),
        )
        .result()
    )


def _deploy_rest(profile, name, model, version, fmt, sku, capacity, provider_data):
    """Call ARM directly: the SDK lacks modelProviderData, which Anthropic models require."""
    token = credential(profile).get_token(ARM_SCOPE).token
    url = (
        f"https://management.azure.com/subscriptions/{profile.subscription_id}"
        f"/resourceGroups/{profile.resource_group}/providers/Microsoft.CognitiveServices"
        f"/accounts/{profile.account}/deployments/{name}?api-version=2025-10-01-preview"
    )
    body = {
        "sku": {"name": sku, "capacity": capacity},
        "properties": {
            "model": {"format": fmt, "name": model, "version": version},
            "modelProviderData": provider_data,
        },
    }
    resp = requests.put(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Deployment failed ({resp.status_code}): {resp.text}")
    return resp.json()


def delete(profile: Profile, name: str) -> None:
    client(profile).deployments.begin_delete(profile.resource_group, profile.account, name).result()


def get_key(profile: Profile) -> str:
    keys = client(profile).accounts.list_keys(profile.resource_group, profile.account)
    return keys.key1


def endpoint(profile: Profile) -> str:
    acct = client(profile).accounts.get(profile.resource_group, profile.account)
    return acct.properties.endpoint.rstrip("/")
