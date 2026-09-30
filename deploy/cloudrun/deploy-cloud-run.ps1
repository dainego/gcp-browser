param(
    [string]$ProjectId = "",
    [string]$Region = "us-east4",
    [string]$ServiceName = "gcs-data-browser",
    [string]$RuntimeServiceAccount = "",
    [string]$ArtifactRepository = "gcp-browser",
    [string]$ImageTag = "latest",
    [switch]$AllowUnauthenticated
)

$ErrorActionPreference = "Stop"

# Script location: <project-root>\deploy\cloudrun
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

function Require-Gcloud {
    if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
        throw "gcloud CLI no está instalado o no está en PATH."
    }
}

function Get-CurrentProject {
    $value = (& gcloud config get-value project 2>$null).Trim()
    if ($value -and $value -ne "(unset)") { return $value }
    return ""
}

function Secret-Exists([string]$SecretName) {
    & gcloud secrets describe $SecretName --project=$ProjectId *> $null
    return ($LASTEXITCODE -eq 0)
}

Require-Gcloud

if (-not $ProjectId) { $ProjectId = Get-CurrentProject }
if (-not $ProjectId) { $ProjectId = Read-Host "Google Cloud Project ID" }
if (-not $ProjectId) { throw "Project ID es obligatorio." }

& gcloud config set project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "No se pudo seleccionar el proyecto." }

if (-not $RuntimeServiceAccount) {
    $RuntimeServiceAccount = "gcpbrowser-cloudrun@$ProjectId.iam.gserviceaccount.com"
}

Write-Host ""
Write-Host "Proyecto:             $ProjectId"
Write-Host "Región:               $Region"
Write-Host "Servicio:             $ServiceName"
Write-Host "Runtime Service Acct: $RuntimeServiceAccount"
Write-Host "Artifact Registry:    $ArtifactRepository"
Write-Host ""

$storagesPath = Join-Path $ProjectRoot "config\storages.json"
if (-not (Test-Path $storagesPath)) { throw "No existe $storagesPath." }

$storages = Get-Content $storagesPath -Raw | ConvertFrom-Json
$secretMappings = New-Object System.Collections.Generic.List[string]

foreach ($property in $storages.PSObject.Properties) {
    $storageId = $property.Name
    $config = $property.Value
    $secretName = [string]$config.secret
    $secretEnv = [string]$config.secret_env

    if (-not $secretName) {
        throw "Storage '$storageId' no tiene 'secret' configurado en storages.json."
    }
    if (-not $secretEnv) {
        throw "Storage '$storageId' no tiene 'secret_env' configurado en storages.json."
    }
    if (-not (Secret-Exists $secretName)) {
        throw "El secret '$secretName' no existe en el proyecto '$ProjectId'."
    }

    Write-Host "Secret existente: $secretName -> ENV $secretEnv"
    $secretMappings.Add("$secretEnv=$secretName`:latest")
}

$image = "${Region}-docker.pkg.dev/${ProjectId}/${ArtifactRepository}/${ServiceName}:${ImageTag}"

Write-Host ""
Write-Host "Construyendo imagen: $image"
Write-Host ""

& gcloud builds submit . `
    --tag $image `
    --project=$ProjectId
if ($LASTEXITCODE -ne 0) { throw "La construcción de la imagen falló." }

Write-Host ""
Write-Host "Desplegando imagen en Cloud Run..."
Write-Host ""

$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--image", $image,
    "--project", $ProjectId,
    "--region", $Region,
    "--platform", "managed",
    "--service-account", $RuntimeServiceAccount,
    "--set-secrets", ($secretMappings -join ","),
    "--no-allow-unauthenticated"
)

if ($AllowUnauthenticated) {
    $deployArgs[$deployArgs.IndexOf("--no-allow-unauthenticated")] = "--allow-unauthenticated"
}

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "El despliegue de Cloud Run falló." }

Write-Host ""
Write-Host "Despliegue finalizado."
& gcloud run services describe $ServiceName --project=$ProjectId --region=$Region --format="value(status.url)"
