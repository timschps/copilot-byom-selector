"""Per-profile Entra authentication with isolated, persistent token caches."""

from __future__ import annotations

from azure.identity import (
    AuthenticationRecord,
    DeviceCodeCredential,
    TokenCachePersistenceOptions,
)

from .config import Profile, home

ARM_SCOPE = "https://management.azure.com/.default"


def _record_path(profile: Profile):
    return home() / f"auth-{profile.name}.json"


def credential(profile: Profile) -> DeviceCodeCredential:
    record = None
    path = _record_path(profile)
    if path.exists():
        record = AuthenticationRecord.deserialize(path.read_text(encoding="utf-8"))
    return DeviceCodeCredential(
        tenant_id=profile.tenant_id,
        authentication_record=record,
        cache_persistence_options=TokenCachePersistenceOptions(name=f"byom-{profile.name}"),
    )


def login(profile: Profile) -> str:
    cred = credential(profile)
    record = cred.authenticate(scopes=[ARM_SCOPE])
    _record_path(profile).write_text(record.serialize(), encoding="utf-8")
    return record.username
