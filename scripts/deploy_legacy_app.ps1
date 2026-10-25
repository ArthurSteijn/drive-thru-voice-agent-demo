[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-drivethru-prod",
    [string]$ExistingAppName = "ca-web-bseesl42xejvq",
    [string]$LegacyAppName = "ca-web-legacy",
    [string]$LegacyImage = "crbseesl42xejvq.azurecr.io/voiceliveapi-drivethru-agent-demo/web-drivethru-prod:azd-deploy-1792758139"
)

$ErrorActionPreference = "Stop"

Write-Host "Fetching existing Fabric connection string..." -ForegroundColor Yellow
$appJson = az containerapp show -g $ResourceGroup -n $ExistingAppName -o json | ConvertFrom-Json
$fabricEnv = $appJson.properties.template.containers[0].env | Where-Object { $_.name -eq "FABRIC_CONNECTION_STRING" }
$fabricConn = if ($fabricEnv) { $fabricEnv.value } else { "" }

Write-Host "Deploying permanent legacy app '$LegacyAppName'..." -ForegroundColor Yellow
$deployment = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file infra/side-by-side.bicep `
    --parameters `
        appName=$LegacyAppName `
        imageName=$LegacyImage `
        agentName="drivethru-ordering-agent" `
        agentVersion="2" `
        voiceLiveApiVersion="2026-04-10" `
        foundryFeatures="" `
        fabricConnectionString=$fabricConn `
    --query "{url:properties.outputs.appUrl.value, name:properties.outputs.appName.value}" `
    -o json | ConvertFrom-Json

Write-Host "`nLegacy App Deployed Successfully!" -ForegroundColor Green
Write-Host "URL: $($deployment.url)" -ForegroundColor Cyan
Write-Host "Agent: drivethru-ordering-agent (kind=prompt, legacy architecture)`n" -ForegroundColor DarkGray
