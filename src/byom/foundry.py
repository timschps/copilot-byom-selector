"""Model management against an Azure AI Foundry (Cognitive Services AIServices) account."""

from __future__ import annotations

from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import (
    Deployment,
    DeploymentModel,
    DeploymentProperties,
    Sku,
)

from .auth import credential
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
):
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


def delete(profile: Profile, name: str) -> None:
    client(profile).deployments.begin_delete(profile.resource_group, profile.account, name).result()


def get_key(profile: Profile) -> str:
    keys = client(profile).accounts.list_keys(profile.resource_group, profile.account)
    return keys.key1


def endpoint(profile: Profile) -> str:
    acct = client(profile).accounts.get(profile.resource_group, profile.account)
    return acct.properties.endpoint.rstrip("/")
