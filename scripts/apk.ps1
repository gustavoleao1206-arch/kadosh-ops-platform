<#
.SYNOPSIS
  Gera o APK do app do sócio.

.DESCRIPTION
  O endereço do servidor entra em tempo de build. Sem -Api, o app aponta para http://10.0.2.2:8000,
  que é o host desta máquina visto de DENTRO do emulador Android — num celular de verdade isso não
  conecta em lugar nenhum.

.EXAMPLE
  scripts\apk.ps1
  scripts\apk.ps1 -Debug
  scripts\apk.ps1 -Api https://kadosh.onrender.com
#>
param(
  [string]$Api = "",
  [switch]$Debug,
  # Só para o emulador desta máquina. Existe para que o release "de verdade" NUNCA saia por
  # descuido apontando para 10.0.2.2 — quem quer o APK de teste precisa dizer que quer.
  [switch]$Emulador
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Mobile = Join-Path $Root "mobile"

$env:PATH = "X:\dev\tools\flutter\bin;$env:PATH"
$env:JAVA_HOME = "X:\dev\tools\jdk17"
$env:ANDROID_SDK_ROOT = "X:\dev\tools\android-sdk"

# O NDK não vem pelo sdkmanager nesta máquina (ver docs/RUNBOOK.md). Falhar aqui, com a mensagem
# certa, é melhor do que deixar o Gradle morrer com 0xC0000409 dez minutos depois.
$ndk = Join-Path $env:ANDROID_SDK_ROOT "ndk\28.2.13676358\source.properties"
if (-not (Test-Path $ndk)) {
  Write-Error "NDK 28.2.13676358 não está instalado. Rode scripts\instalar-ndk.ps1 primeiro."
  exit 1
}

# O endereço do servidor entra no BINÁRIO. Um release sem -Api sai apontando para 10.0.2.2 (o host
# visto de dentro do emulador) e, no celular do sócio, não conecta em lugar nenhum — o RUNBOOK
# chegou a documentar exatamente esse comando como "o que o sócio instala". Agora o script recusa.
if (-not $Debug -and -not $Api -and -not $Emulador) {
  Write-Error @"
Release sem -Api. Este APK sairia apontando para http://10.0.2.2:8000 — o emulador desta máquina —
e no celular do sócio não conectaria em lugar nenhum.

  Para o sócio:    scripts\apk.ps1 -Api https://SEU-APP.onrender.com
  Para o emulador: scripts\apk.ps1 -Emulador
"@
  exit 1
}

if ($Emulador -and -not $Api) { $Api = "http://10.0.2.2:8000" }

# Senha trafegando em claro é o risco concreto: o login manda e-mail e senha no corpo. Endereço
# local (emulador, rede da loja) é aceitável em http; a internet, não.
if (-not $Debug -and $Api -match '^http://' -and $Api -notmatch '^http://(10\.|127\.|192\.168\.|localhost)') {
  Write-Error "Release apontando para http:// na internet ($Api). A senha do sócio iria em texto puro no login. Use https://."
  exit 1
}

$args = @("build", "apk")
$args += if ($Debug) { "--debug" } else { "--release" }
if ($Api) { $args += "--dart-define=KADOSH_API=$Api" }

Push-Location $Mobile
try {
  Write-Host "flutter $($args -join ' ')" -ForegroundColor DarkGray
  # O Flutter escreve avisos no stderr (o clássico "SDK XML version 4 was encountered"). Com
  # $ErrorActionPreference = "Stop", o PowerShell 5.1 transforma QUALQUER linha de stderr de um
  # executável em erro terminante — e o build morria com o APK pronto no disco, por causa de um
  # aviso. Quem manda aqui é o código de saída, não o stderr.
  $antes = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & flutter @args
  $codigo = $LASTEXITCODE
  $ErrorActionPreference = $antes
  if ($codigo -ne 0) { exit $codigo }

  $nome = if ($Debug) { "app-debug.apk" } else { "app-release.apk" }
  $apk = Join-Path $Mobile "build\app\outputs\flutter-apk\$nome"
  if (Test-Path $apk) {
    $mb = [math]::Round((Get-Item $apk).Length / 1MB, 1)

    # O template do Flutter declara INTERNET só nos manifestos de debug e profile. Um release sem
    # ela instala, abre, desenha tudo e nunca conecta — dizendo "Sem conexão com o servidor" para
    # sempre. Já aconteceu aqui. O APK não sai desta função sem essa checagem.
    $aapt2 = Get-ChildItem (Join-Path $env:ANDROID_SDK_ROOT "build-tools") -Recurse -Filter aapt2.exe -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($aapt2) {
      $antes = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $perms = & $aapt2.FullName dump permissions $apk 2>$null
      $ErrorActionPreference = $antes
      if (-not ($perms | Select-String -SimpleMatch "android.permission.INTERNET")) {
        Write-Error "O APK saiu SEM android.permission.INTERNET — ele nunca vai conectar. Confira mobile/android/app/src/main/AndroidManifest.xml."
        exit 1
      }
      Write-Host "Permissão de internet: ok" -ForegroundColor DarkGray
    } else {
      Write-Warning "aapt2 não encontrado; não deu para conferir a permissão de internet do APK."
    }

    Write-Host ""
    Write-Host "APK pronto: $apk  ($mb MB)" -ForegroundColor Green
    Write-Host "Servidor embutido: $(if ($Api) { $Api } else { 'http://10.0.2.2:8000 (padrão)' })" -ForegroundColor DarkGray
    if ($Emulador) {
      Write-Host "ATENÇÃO: build de emulador. NÃO instale este APK no celular do sócio." -ForegroundColor Yellow
    }
  }
}
finally {
  Pop-Location
}
