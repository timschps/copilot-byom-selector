targetScope = 'resourceGroup'

@description('Name of the Foundry (Azure AI Services) account. Also used as the custom subdomain, so it must be globally unique.')
@minLength(2)
@maxLength(64)
param accountName string

@description('Azure region. Pick one that offers the models you want to deploy.')
param location string = resourceGroup().location

@description('Model deployments to create. Each item: { name, model: { format, name, version }, sku: { name, capacity } }.')
param deployments array = [
  {
    name: 'gpt-4-1'
    model: { format: 'OpenAI', name: 'gpt-4.1', version: '2025-04-14' }
    sku: { name: 'GlobalStandard', capacity: 10 }
  }
]

@description('Disable key-based authentication. The local gateway currently uses keys, so keep false unless you add Entra token support.')
param disableLocalAuth bool = false

@allowed([ 'Enabled', 'Disabled' ])
param publicNetworkAccess string = 'Enabled'

param tags object = {}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: publicNetworkAccess
    disableLocalAuth: disableLocalAuth
  }
}

// Deployments on one account must be created sequentially.
@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for d in deployments: {
  parent: account
  name: d.name
  sku: d.sku
  properties: {
    model: d.model
  }
}]

output accountName string = account.name
output endpoint string = account.properties.endpoint
output deploymentNames array = [for (d, i) in deployments: modelDeployments[i].name]
