# Setting up Foundry resources

Two supported paths. Use Bicep for the initial, reviewable setup; use the CLI for day-to-day model changes.

## Option A: Bicep (recommended for the account)

Prerequisites: Azure CLI with Bicep, an Azure subscription in the target tenant, *Contributor* on a resource group.

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>
az group create -n rg-byom -l swedencentral

Copy-Item infra\main.example.bicepparam infra\main.local.bicepparam   # git-ignored
# edit accountName and deployments

az deployment group create -g rg-byom -f infra\main.bicep -p infra\main.local.bicepparam
```

The outputs give the account name and endpoint. Register it as a profile:

```powershell
byom profile add priv --tenant-id <tenant-id> --subscription-id <subscription-id> `
  --resource-group rg-byom --account <accountName>
```

## Option B: CLI only

If the Foundry account already exists (created in the portal or by someone else), skip Bicep and add the profile.
Manage deployments with:

```powershell
byom login priv
byom list priv
byom deploy priv gpt41 --model gpt-4.1 --version 2025-04-14
byom delete priv gpt41
byom sync
```

Creating the account itself from the CLI is intentionally not supported: resource creation belongs in Bicep so it stays declarative and reviewable.

## Permissions

| Action | Role |
| --- | --- |
| Create account (Bicep) | Contributor on the resource group |
| Manage deployments, read keys (`byom`) | Cognitive Services Contributor on the account |

## Multiple tenants (personal vs. work)

Create one profile per tenant. Costs land in the subscription that owns the account, so use a personal subscription for
personal use. Each profile has its own token cache, so signing in to one tenant never affects another.

```powershell
byom profile add work --tenant-id <work-tenant> --subscription-id <...> --resource-group <...> --account <...>
byom profile add priv --tenant-id <personal-tenant> --subscription-id <...> --resource-group rg-byom --account <...>
byom login work; byom login priv
byom sync            # aliases: work-<deployment>, priv-<deployment>
```

Check your employer's policy before sending code or prompts to a non-corporate tenant.
