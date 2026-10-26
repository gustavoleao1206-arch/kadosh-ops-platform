<#
.SYNOPSIS
  Sobe o ambiente de desenvolvimento do backend com um comando.

.DESCRIPTION
  1. Inicia o PostgreSQL portátil (porta 5433)
  2. Cria o ambiente Python (.venv) se não existir e instala as dependências fixadas
  3. Aplica as migrations
  4. (opcional) Aplica o seed de demonstração
  5. Sobe a API em http://localhost:8000 (documentação em /api/docs)

.EXAMPLE
  scripts\dev.ps1            # sobe tudo
  scripts\dev.ps1 -Seed      # sobe tudo e aplica dados de demonstração
#>
param([switch]$Seed)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

& "$PSScriptRoot\db.ps1" start
if ($LASTEXITCODE -ne 0) { exit 1 }

if (-not (Test-Path $Py)) {
  Write-Host "Criando ambiente Python em backend\.venv ..."
  $env:PIP_CACHE_DIR = "X:\dev\cache\pip"
  python -m venv (Join-Path $Backend ".venv")
  & $Py -m pip install --upgrade pip -q
  & $Py -m pip install -r (Join-Path $Backend "requirements.txt") -q
}

if (-not (Test-Path (Join-Path $Backend ".env"))) {
  Copy-Item (Join-Path $Backend ".env.example") (Join-Path $Backend ".env")
  Write-Host "Criado backend\.env a partir do .env.example"
}

Push-Location $Backend
try {
  Write-Host "Aplicando migrations ..."
  & $Py -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { exit 1 }

  if ($Seed) {
    Write-Host "Aplicando seed de demonstração ..."
    & $Py -m app.cli seed-demo
  }

  Write-Host ""
  Write-Host "API:  http://localhost:8000/api/v1/health"
  Write-Host "Docs: http://localhost:8000/api/docs"
  Write-Host ""
  & $Py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}
finally {
  Pop-Location
}
