<#
.SYNOPSIS
  Gera um backup do banco (formato custom do pg_dump) em backups\kadosh-AAAA-MM-DD_HHmm.dump.

.DESCRIPTION
  Por padrão usa o banco local (kadosh_dev). Para produção, passe a URL externa do Render:
    scripts\backup.ps1 -Url "postgresql://usuario:senha@host.render.com/banco"
  O banco de produção não aceita conexão externa (ipAllowList vazio no render.yaml): libere o seu
  IP em kadosh-db -> Networking só durante o backup e apague a regra em seguida.
  O dump tem nome, telefone e placa de clientes: guarde-o CIFRADO (7-Zip com AES, BitLocker), nunca
  numa pasta sincronizada em texto claro. Mantém as 8 cópias mais recentes.

  Restaurar num banco vazio:
    X:\dev\pgsql\bin\pg_restore -d "<URL>" --no-owner --no-privileges backups\kadosh-....dump
#>
param(
  [string]$Url = "postgresql://kadosh:kadosh_dev@localhost:5433/kadosh_dev",
  [string]$OutDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "backups"),
  [int]$Keep = 8
)

$ErrorActionPreference = "Stop"
$PgDump = "X:\dev\pgsql\bin\pg_dump.exe"
if (-not (Test-Path $PgDump)) { Write-Error "pg_dump não encontrado em $PgDump"; exit 1 }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$file = Join-Path $OutDir "kadosh-$stamp.dump"

& $PgDump --format=custom --no-owner --no-privileges --file=$file $Url
if ($LASTEXITCODE -ne 0) { Write-Error "Falha no pg_dump"; exit 1 }

$size = [math]::Round((Get-Item $file).Length / 1KB, 1)
Write-Host "Backup gerado: $file ($size KB)"

Get-ChildItem $OutDir -Filter "kadosh-*.dump" | Sort-Object LastWriteTime -Descending |
  Select-Object -Skip $Keep | ForEach-Object { Remove-Item $_.FullName -Confirm:$false; Write-Host "Removido antigo: $($_.Name)" }
