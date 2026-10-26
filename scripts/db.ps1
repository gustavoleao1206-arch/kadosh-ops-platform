<#
.SYNOPSIS
  Controla o PostgreSQL portátil do projeto (sem Docker, sem serviço do Windows).

.EXAMPLE
  scripts\db.ps1 start     # sobe o banco na porta 5433
  scripts\db.ps1 stop
  scripts\db.ps1 status
  scripts\db.ps1 psql      # abre o psql já conectado em kadosh_dev
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("start", "stop", "status", "restart", "psql")]
  [string]$Action = "status"
)

$PgBin  = "X:\dev\pgsql\bin"
$PgData = "X:\dev\pgdata"
$PgLog  = "X:\dev\pgdata\server.log"
$PgPort = 5433

if (-not (Test-Path "$PgBin\pg_ctl.exe")) {
  Write-Error "PostgreSQL não encontrado em $PgBin. Veja docs/RUNBOOK.md (seção 'Banco local')."
  exit 1
}

switch ($Action) {
  "start" {
    & "$PgBin\pg_ctl.exe" -D $PgData status *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "Banco já está rodando (porta $PgPort)."; exit 0 }
    & "$PgBin\pg_ctl.exe" -D $PgData -l $PgLog -w start
    if ($LASTEXITCODE -ne 0) { Write-Error "Falha ao iniciar. Veja $PgLog"; exit 1 }
    Write-Host "Banco iniciado na porta $PgPort."
  }
  "stop" {
    & "$PgBin\pg_ctl.exe" -D $PgData -m fast -w stop
  }
  "restart" {
    & "$PgBin\pg_ctl.exe" -D $PgData -l $PgLog -m fast -w restart
  }
  "status" {
    & "$PgBin\pg_ctl.exe" -D $PgData status
  }
  "psql" {
    $env:PGPASSWORD = "kadosh_dev"
    & "$PgBin\psql.exe" -h localhost -p $PgPort -U kadosh -d kadosh_dev
  }
}
