<#
.SYNOPSIS
Deploys the new Voice Agent architecture as a separate Azure Container App (ca-web-voiceagent)
side-by-side with Main, reusing all existing infrastructure.

.DESCRIPTION
Reuses:
- Resource Group: rg-drivethru-prod
- Container Apps Environment: cae-bseesl42xejvq
- Azure Container Registry: crbseesl42xejvq
- User-Assigned Managed Identity: id-bseesl42xejvq (with existing RBAC roles)
- Microsoft Fabric Database connection string
- Azure AI Foundry Project: proj-voiceliveapi-demo (drivethru-voice-agent)

Creates:
- Container Image: crbseesl42xejvq.azurecr.io/voiceliveapi-drivethru-agent-demo/web:feat-voice-agent
- Container App: ca-web-voiceagent
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-drivethru-prod",
    [string]$AcrName = "crbseesl42xejvq",
    [string]$AppName = "ca-web-voiceagent",
    [string]$ExistingAppName = "ca-web-bseesl42xejvq",
    [string]$ImageTag = "feat-voice-agent",
    [switch]$SkipBuild = $false
)

$ErrorActionPreference = "Stop"

# Ensure UTF-8 output so Azure CLI log streaming does not fail on unicode characters (e.g. checkmarks)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   Side-by-Side Azure Deployment: Voice Agent v1       " -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

# Step 1: Check Azure CLI login
Write-Host "[1/4] Checking Azure CLI login..." -ForegroundColor Yellow
$account = az account show --query "{subId:id, name:name}" -o json | ConvertFrom-Json
if (-not $account) {
    Write-Error "Not logged in to Azure CLI. Run 'az login' first."
}
Write-Host "Active Subscription: $($account.name) ($($account.subId))`n" -ForegroundColor Green

# Step 2: Build Container Image via ACR Remote Build (if not skipped)
$imageFull = "$AcrName.azurecr.io/voiceliveapi-drivethru-agent-demo/web:$ImageTag"
if ($SkipBuild) {
    Write-Host "[2/4] Skipping build as requested. Reusing existing image: $imageFull`n" -ForegroundColor Green
} else {
    Write-Host "[2/4] Building container image remotely in ACR ($AcrName)..." -ForegroundColor Yellow
    az acr build --registry $AcrName --image "voiceliveapi-drivethru-agent-demo/web:$ImageTag" .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ACR remote build failed."
    }
    Write-Host "Image built successfully: $imageFull`n" -ForegroundColor Green
}

# Step 3: Fetch existing production environment variables (e.g. Fabric connection string)
Write-Host "[3/4] Reusing Fabric DB connection string from existing app ($ExistingAppName)..." -ForegroundColor Yellow
$fabricConn = az containerapp show `
    --resource-group $ResourceGroup `
    --name $ExistingAppName `
    --query "properties.template.containers[0].env[?name=='FABRIC_CONNECTION_STRING'].value | [0]" `
    -o tsv

if (-not $fabricConn) {
    Write-Host "Warning: No FABRIC_CONNECTION_STRING found in $ExistingAppName. Will fallback to menu seed." -ForegroundColor Magenta
    $fabricConn = ""
} else {
    Write-Host "Successfully retrieved Fabric connection string.`n" -ForegroundColor Green
}

# Step 4: Deploy Bicep template
Write-Host "[4/4] Deploying Container App '$AppName' via Bicep..." -ForegroundColor Yellow
$deployment = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file infra/side-by-side.bicep `
    --parameters `
        appName=$AppName `
        imageName=$imageFull `
        fabricConnectionString=$fabricConn `
    --query "{url:properties.outputs.appUrl.value, name:properties.outputs.appName.value}" `
    -o json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Bicep deployment failed."
}

$mainUrl = az containerapp show `
    --resource-group $ResourceGroup `
    --name $ExistingAppName `
    --query "properties.configuration.ingress.fqdn" `
    -o tsv

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "              DEPLOYMENT SUCCESSFUL!                    " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "`nSide-by-Side Comparison URLs:" -ForegroundColor White
Write-Host "  Main (Legacy Prompt Agent):" -ForegroundColor DarkGray
Write-Host "    https://$mainUrl" -ForegroundColor Cyan
Write-Host "    Agent: drivethru-ordering-agent (kind=prompt)`n" -ForegroundColor DarkGray
Write-Host "  Feature Branch (New Voice Agent v1):" -ForegroundColor DarkGray
Write-Host "    $($deployment.url)" -ForegroundColor Yellow
Write-Host "    Agent: drivethru-voice-agent (kind=voice, deep noise suppression, semantic VAD)`n" -ForegroundColor DarkGray
