using 'main.bicep'

// Copy to main.local.bicepparam (git-ignored) and adjust.
param accountName = 'my-byom-foundry'
param deployments = [
  {
    name: 'gpt-4-1'
    model: { format: 'OpenAI', name: 'gpt-4.1', version: '2025-04-14' }
    sku: { name: 'GlobalStandard', capacity: 10 }
  }
]
