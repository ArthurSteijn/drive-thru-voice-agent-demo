@description('Name of the new Container App for the Voice Agent preview')
param appName string = 'ca-web-voiceagent'

@description('Location matching existing resources')
param location string = 'westeurope'

@description('Existing Container Apps Environment name')
param containerAppsEnvironmentName string = 'cae-bseesl42xejvq'

@description('Existing Azure Container Registry name')
param containerRegistryName string = 'crbseesl42xejvq'

@description('Existing User-Assigned Managed Identity name')
param identityName string = 'id-bseesl42xejvq'

@description('Container image URL to deploy')
param imageName string = 'crbseesl42xejvq.azurecr.io/voiceliveapi-drivethru-agent-demo/web:feat-voice-agent'

@description('Agent Name in Azure AI Foundry (kind=voice)')
param agentName string = 'drivethru-voice-agent'

@description('Agent Version in Azure AI Foundry')
param agentVersion string = '1'

@description('Azure AI Foundry Project Name')
param projectName string = 'proj-voiceliveapi-demo'

@description('Foundry VoiceLive endpoint URL')
param voiceLiveEndpoint string = 'https://aif-voiceliveapi-demo.services.ai.azure.com'

@description('Voice Agent API Version')
param voiceLiveApiVersion string = 'v1'

@description('Foundry preview features header flag')
param foundryFeatures string = 'VoiceAgents=V1Preview'

@description('Model deployment name')
param modelDeploymentName string = 'gpt-5.4'

@secure()
@description('Fabric or SQL database connection string')
param fabricConnectionString string = ''

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  tags: {
    'azd-service-name': 'web'
    branch: 'feat-voice-agent-architecture'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: imageName
          resources: {
            cpu: json('1.0')
            memory: '2.0Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentity.properties.clientId
            }
            {
              name: 'VOICELIVE_ENDPOINT'
              value: voiceLiveEndpoint
            }
            {
              name: 'AGENT_NAME'
              value: agentName
            }
            {
              name: 'VOICE_AGENT_NAME'
              value: agentName
            }
            {
              name: 'AGENT_VERSION'
              value: agentVersion
            }
            {
              name: 'PROJECT_NAME'
              value: projectName
            }
            {
              name: 'VOICE_AGENT_API_VERSION'
              value: voiceLiveApiVersion
            }
            {
              name: 'FOUNDRY_FEATURES'
              value: foundryFeatures
            }
            {
              name: 'PROJECT_ENDPOINT'
              value: '${voiceLiveEndpoint}/api/projects/${projectName}'
            }
            {
              name: 'MODEL_DEPLOYMENT_NAME'
              value: modelDeploymentName
            }
            {
              name: 'FABRIC_CONNECTION_STRING'
              value: fabricConnectionString
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 5
      }
    }
  }
}

output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output appName string = app.name
