targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resources')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('VoiceLive endpoint URL (e.g. https://<project>.services.ai.azure.com)')
param voiceLiveEndpoint string = ''

@description('Agent Name created in Azure AI Foundry')
param agentName string = 'drivethru-voice-agent'

@description('Agent Version pinned in Azure AI Foundry')
param agentVersion string = '1'

@description('Azure AI Foundry Project Name')
param projectName string = ''

@description('VoiceLive API Version')
param voiceLiveApiVersion string = 'v1'

@description('Foundry preview features header flag')
param foundryFeatures string = 'VoiceAgents=V1Preview'

@description('Fabric or Azure SQL connection string (leave empty if using seed fallback or Managed Identity)')
param fabricConnectionString string = ''

@description('Resource group hosting the Azure AI Foundry resource (e.g. rg-voiceliveapi-demo)')
param foundryResourceGroupName string = 'rg-voiceliveapi-demo'

var abbrs = {
  resourcesResourceGroups: 'rg-'
  appManagedEnvironments: 'cae-'
  appContainerApps: 'ca-'
  containerRegistryRegistries: 'cr'
  operationalInsightsWorkspaces: 'log-'
  managedIdentityUserAssignedIdentities: 'id-'
}

var tags = {
  'azd-env-name': environmentName
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

module managedIdentity './core/security/managed-identity.bicep' = {
  name: 'managed-identity'
  scope: rg
  params: {
    name: '${abbrs.managedIdentityUserAssignedIdentities}${resourceToken}'
    location: location
    tags: tags
  }
}

module logAnalytics './core/monitor/loganalytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    name: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    location: location
    tags: tags
  }
}

module containerRegistry './core/host/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
  }
}

module containerAppsEnvironment './core/host/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: rg
  params: {
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceName: logAnalytics.outputs.name
  }
}

module app './app/web.bicep' = {
  name: 'web'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}web-${resourceToken}'
    location: location
    tags: tags
    containerAppsEnvironmentName: containerAppsEnvironment.outputs.name
    containerRegistryName: containerRegistry.outputs.name
    identityId: managedIdentity.outputs.id
    identityClientId: managedIdentity.outputs.clientId
    voiceLiveEndpoint: voiceLiveEndpoint
    agentName: agentName
    agentVersion: agentVersion
    projectName: projectName
    voiceLiveApiVersion: voiceLiveApiVersion
    foundryFeatures: foundryFeatures
    fabricConnectionString: fabricConnectionString
  }
}

// Grant the Managed Identity permissions on the Container Registry
module acrPullRole './core/security/role.bicep' = {
  name: 'acr-pull-role'
  scope: rg
  params: {
    principalId: managedIdentity.outputs.principalId
    roleDefinitionId: '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    principalType: 'ServicePrincipal'
  }
}

// Grant Cognitive Services User role to Managed Identity for VoiceLive
module cogServicesRole './core/security/role.bicep' = {
  name: 'cog-services-role'
  scope: rg
  params: {
    principalId: managedIdentity.outputs.principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User
    principalType: 'ServicePrincipal'
  }
}

// Grant Azure AI Developer role to Managed Identity for Foundry Agent access
module aiDeveloperRole './core/security/role.bicep' = {
  name: 'ai-developer-role'
  scope: rg
  params: {
    principalId: managedIdentity.outputs.principalId
    roleDefinitionId: '64702f94-c441-49e6-a78b-ef80e0188fee' // Azure AI Developer
    principalType: 'ServicePrincipal'
  }
}

// Existing Foundry Resource Group (for cross-region / cross-RG role assignments)
resource foundryRg 'Microsoft.Resources/resourceGroups@2022-09-01' existing = if (!empty(foundryResourceGroupName)) {
  name: foundryResourceGroupName
}

// Grant Cognitive Services User role to Managed Identity on the Foundry RG
module foundryCogServicesRole './core/security/role.bicep' = if (!empty(foundryResourceGroupName)) {
  name: 'foundry-cog-services-role'
  scope: foundryRg
  params: {
    principalId: managedIdentity.outputs.principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User
    principalType: 'ServicePrincipal'
  }
}

// Grant Azure AI Developer role to Managed Identity on the Foundry RG
module foundryAiDeveloperRole './core/security/role.bicep' = if (!empty(foundryResourceGroupName)) {
  name: 'foundry-ai-developer-role'
  scope: foundryRg
  params: {
    principalId: managedIdentity.outputs.principalId
    roleDefinitionId: '64702f94-c441-49e6-a78b-ef80e0188fee' // Azure AI Developer
    principalType: 'ServicePrincipal'
  }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output APPLICATION_URL string = app.outputs.uri
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output MANAGED_IDENTITY_CLIENT_ID string = managedIdentity.outputs.clientId
output MANAGED_IDENTITY_PRINCIPAL_ID string = managedIdentity.outputs.principalId
