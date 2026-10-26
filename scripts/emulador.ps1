<#
.SYNOPSIS
  Sobe o emulador Android e, opcionalmente, instala e abre o app.

.DESCRIPTION
  O AVD mora em X:\dev\avd (e não no perfil do usuário) por dois motivos: o SSD principal desta
  máquina está apertado — um emulador ocupa vários GB — e o perfil do usuário aqui tem filtro de
  antivírus que já causou dor de cabeça (ver docs/RUNBOOK.md).

  Dentro do emulador, 10.0.2.2 é o host. O `dev.ps1` já sobe o uvicorn em 0.0.0.0, então funciona
  direto — não precisa de túnel nem de regra de firewall.

  Por isso o APK de teste é gerado assim:
      scripts\apk.ps1 -Api http://10.0.2.2:8000

  (Se um dia der "Sem conexão" no app, a primeira coisa a conferir NÃO é rede: é se o APK tem a
  permissão de internet — `aapt2 dump permissions app-release.apk`. Ver docs/RUNBOOK.md.)

.EXAMPLE
  scripts\emulador.ps1
  scripts\emulador.ps1 -Instalar
  scripts\emulador.ps1 -Instalar -Debug
  scripts\emulador.ps1 -Parar
#>
param(
  [switch]$Instalar,
  [switch]$Debug,
  [switch]$Parar,
  [string]$Avd = "kadosh"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Sdk = "X:\dev\tools\android-sdk"
$Adb = Join-Path $Sdk "platform-tools\adb.exe"

# Na PRIMEIRA chamada depois de um reinicio da maquina, o adb escreve "* daemon not running;
# starting now" no STDERR. Com ErrorActionPreference=Stop o PowerShell 5.1 trata essa linha como
# erro fatal, e o script morria antes de fazer qualquer coisa — sempre na primeira vez do dia, que
# e justamente quando se quer testar. Subir o daemon antes, com o erro silenciado, resolve na
# origem; da segunda vez em diante ele nao imprime nada e este bloco custa milissegundos.
if (Test-Path $Adb) {
  $ErrorActionPreference = "Continue"
  & $Adb start-server 2>&1 | Out-Null
  $ErrorActionPreference = "Stop"
}
$env:ANDROID_SDK_ROOT = $Sdk
$env:ANDROID_HOME = $Sdk
$env:ANDROID_AVD_HOME = "X:\dev\avd"

if ($Parar) {
  & $Adb emu kill 2>$null
  Write-Host "Emulador encerrado."
  exit 0
}

# ---------------------------------------------------------------- subir

$jaLigado = (& $Adb devices | Select-String '^emulator-\d+\s+device$') -ne $null
if ($jaLigado) {
  Write-Host "Emulador já está rodando."
} else {
  Write-Host "Subindo o emulador ($Avd)..."
  $emu = Join-Path $Sdk "emulator\emulator.exe"
  # -no-snapshot-load: começar limpo evita depurar um estado salvo de uma execução anterior
  # -no-audio: driver de áudio é fonte gratuita de travamento e aqui não serve para nada
  Start-Process -FilePath $emu `
    -ArgumentList @("-avd", $Avd, "-no-snapshot-load", "-no-audio", "-no-boot-anim") `
    -WindowStyle Normal

  Write-Host "Esperando o Android terminar de bootar (pode levar uns minutos na primeira vez)..."
  & $Adb wait-for-device
  $limite = (Get-Date).AddMinutes(8)
  do {
    Start-Sleep -Seconds 5
    $pronto = (& $Adb shell getprop sys.boot_completed 2>$null | Out-String).Trim()
    if ((Get-Date) -gt $limite) { throw "O emulador não terminou de bootar em 8 minutos." }
  } until ($pronto -eq "1")
  Write-Host "Android pronto." -ForegroundColor Green
}

if (-not $Instalar) { exit 0 }

# ---------------------------------------------------------------- instalar o app

$nome = if ($Debug) { "app-debug.apk" } else { "app-release.apk" }
$apk = Join-Path $Root "mobile\build\app\outputs\flutter-apk\$nome"
if (-not (Test-Path $apk)) {
  Write-Error "$nome não existe. Rode scripts\apk.ps1 primeiro."
  exit 1
}

Write-Host "Instalando $nome ($([math]::Round((Get-Item $apk).Length/1MB,1)) MB)..."
& $Adb install -r $apk
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Abrindo o app..."
# O `monkey` ecoa os proprios argumentos no STDERR mesmo quando da certo. Com
# ErrorActionPreference=Stop isso virava NativeCommandError e o script terminava com codigo 1 —
# com o app ja aberto na tela. Erro que mente sobre o resultado e pior que erro nenhum.
$ErrorActionPreference = "Continue"
& $Adb shell monkey -p br.com.kadosh.kadosh_campo -c android.intent.category.LAUNCHER 1 2>&1 | Out-Null
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "App aberto no emulador." -ForegroundColor Green
Write-Host "Logs:        $Adb logcat -s flutter" -ForegroundColor DarkGray
# `>` do PowerShell adiciona BOM e corrompe o PNG: puxe o arquivo em vez de redirecionar
Write-Host "Screenshot:  $Adb shell screencap -p /sdcard/t.png; $Adb pull /sdcard/t.png" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Suba o backend com scripts\dev.ps1 -Seed e entre como" -ForegroundColor Yellow
Write-Host "socio@kadosh.com.br / socio12345!" -ForegroundColor Yellow
