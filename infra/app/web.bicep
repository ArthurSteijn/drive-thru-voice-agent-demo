param name string
param location string = resourceGroup().location
param tags object = {}
param containerAppsEnvironmentName string
param containerRegistryName string
param identityId string
param identityClientId string
param voiceLiveEndpoint string
param agentName string
param agentVersion string
param projectName string
param voiceLiveApiVersion string
param foundryFeatures string = 'VoiceAgents=V1Preview'
param fabricConnectionString string
param imageName string = ''

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
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
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          image: !empty(imageName) ? imageName : 'mcr.microsoft.com/azuredocs/aci-helloworld:latest'
          name: 'web'
          resources: {
            cpu: json('1.0')
            memory: '2.0Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: identityClientId
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
              name: 'FOUNDRY_FEATURES'
              value: foundryFeatures
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
              name: 'VOICELIVE_API_VERSION'
              value: voiceLiveApiVersion
            }
            {
              name: 'FABRIC_CONNECTION_STRING'
              value: fabricConnectionString
            }
            {
              name: 'PROJECT_ENDPOINT'
              value: '${voiceLiveEndpoint}/api/projects/${projectName}'
            }
            {
              name: 'MODEL_DEPLOYMENT_NAME'
              value: 'gpt-5.4'
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

output id string = app.id
output name string = app.name
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
