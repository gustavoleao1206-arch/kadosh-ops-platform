<#
.SYNOPSIS
  Roda a suíte de testes do backend contra o banco kadosh_test (Postgres local na porta 5433).

.EXAMPLE
  scripts\test.ps1
  scripts\test.ps1 -k auth      # só os testes cujo nome contém "auth"
#>
param([string]$k = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

& "$PSScriptRoot\db.ps1" start
if ($LASTEXITCODE -ne 0) { exit 1 }

Push-Location $Backend
try {
  if ($k) { & $Py -m pytest -q -k $k } else { & $Py -m pytest -q }
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
