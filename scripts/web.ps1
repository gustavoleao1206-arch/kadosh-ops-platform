<#
.SYNOPSIS
  Painel web em modo desenvolvimento (Vite com recarga automática), com proxy de /api para o backend.

.DESCRIPTION
  Rode o backend antes (scripts\dev.ps1). O painel abre em http://localhost:5173.
  Para o build de produção (servido pelo próprio backend em http://localhost:8000): scripts\web.ps1 -Build

.EXAMPLE
  scripts\web.ps1
  scripts\web.ps1 -Build
#>
param([switch]$Build)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root "web"
$env:npm_config_cache = "X:\dev\cache\npm"

Push-Location $Web
try {
  if (-not (Test-Path (Join-Path $Web "node_modules"))) {
    Write-Host "Instalando dependências do painel ..."
    npm ci
  }
  if ($Build) {
    npm run build
    Write-Host ""
    Write-Host "Build em web\dist — o backend serve em http://localhost:8000/"
  } else {
    npm run dev
  }
}
finally {
  Pop-Location
}
