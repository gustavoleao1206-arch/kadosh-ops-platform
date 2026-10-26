<#
.SYNOPSIS
  Instala o emulador Android e uma imagem de sistema, sem passar pelo sdkmanager.

.DESCRIPTION
  Mesma história do NDK (ver docs/RUNBOOK.md): a CLI do SDK morre com 0xC0000409 nesta máquina, e
  os pacotes vêm direto do repositório do Google, com o SHA-1 conferido.

  Além de baixar e extrair, o script escreve o `package.xml` de cada pacote. Esse arquivo é o que o
  `sdkmanager` normalmente gera na instalação, e é por ele que o `avdmanager` sabe o que está
  instalado — sem ele, criar um AVD falha com "emulator package must be installed!" mesmo com o
  emulador ali na pasta. O conteúdo sai do próprio repositório, não de palpite.

  São ~2 GB no total. Rodar de novo é seguro: o que já existe é pulado, e o package.xml é reescrito.

.EXAMPLE
  scripts\instalar-emulador.ps1
  scripts\instalar-emulador.ps1 -ApiLevel 34
#>
param(
  [int]$ApiLevel = 35,
  [string]$Tag = "google_apis",
  [string]$Abi = "x86_64",
  [string]$SdkRoot = "X:\dev\tools\android-sdk"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Base = "https://dl.google.com/android/repository"
$Downloads = "X:\dev\downloads"
New-Item -ItemType Directory -Force $Downloads | Out-Null

function Get-Sha1 {
  # O <checksum> vem com atributo type="sha1". Com atributo, o PowerShell devolve o XmlElement em
  # vez do texto — e comparar isso com um hash nunca bate.
  param($Checksum)
  if ($Checksum -is [System.Xml.XmlElement]) { return $Checksum.InnerText }
  return [string]$Checksum
}

function Get-ArquivoWindows {
  param($Pacote)
  return $Pacote.archives.archive | Where-Object { $_.'host-os' -eq 'windows' } | Select-Object -First 1
}

function Get-Pacote {
  param([string]$Url, [string]$Sha1, [string]$Nome, [long]$Bytes)

  $zip = Join-Path $Downloads $Nome
  if (-not (Test-Path $zip)) {
    Write-Host "  baixando $Nome ($([math]::Round($Bytes/1MB,0)) MB)..."
    Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing
  }
  # 2 GB baixados pela metade viram erro incompreensível lá na frente
  Write-Host "  conferindo integridade..."
  if ((Get-FileHash $zip -Algorithm SHA1).Hash.ToLower() -ne $Sha1.ToLower()) {
    Remove-Item $zip -Force
    throw "Checksum de $Nome não bateu. O arquivo foi apagado; rode de novo."
  }
  return $zip
}

function Expandir {
  param([string]$Zip, [string]$Destino)

  $tmp = Join-Path $env:TEMP ("sdkx-" + [IO.Path]::GetFileNameWithoutExtension($Zip))
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  New-Item -ItemType Directory -Force $tmp | Out-Null
  Write-Host "  extraindo..."
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::ExtractToDirectory($Zip, $tmp)
  $interno = Get-ChildItem $tmp -Directory | Select-Object -First 1
  New-Item -ItemType Directory -Force (Split-Path $Destino) | Out-Null
  if (Test-Path $Destino) { Remove-Item -Recurse -Force $Destino }
  Move-Item $interno.FullName $Destino
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

function Write-PackageXml {
  <#
    Escreve o package.xml que o sdkmanager escreveria. O <localPackage> é o <remotePackage> do
    repositório sem <archives>, <channelRef> e <dependencies> — as três partes que só fazem sentido
    antes de instalar.
  #>
  param($Pacote, $Doc, [string]$Destino)

  $licencaId = $Pacote.'uses-license'.ref
  $licenca = $Doc.DocumentElement.SelectNodes("*[local-name()='license']") |
    Where-Object { $_.id -eq $licencaId } | Select-Object -First 1
  $textoLicenca = if ($licenca) { [System.Security.SecurityElement]::Escape($licenca.InnerText) } else { "" }

  $local = $Pacote.CloneNode($true)
  foreach ($fora in @('archives', 'channelRef', 'dependencies')) {
    $nodes = @($local.SelectNodes("*[local-name()='$fora']"))
    foreach ($n in $nodes) { [void]$local.RemoveChild($n) }
  }
  $corpo = $local.InnerXml

  $xml = @"
<?xml version="1.0" encoding="UTF-8"?>
<ns2:repository xmlns:ns2="http://schemas.android.com/repository/android/common/02" xmlns:generic="http://schemas.android.com/repository/android/generic/02" xmlns:sdk="http://schemas.android.com/sdk/android/repo/repository2/03" xmlns:sys-img="http://schemas.android.com/sdk/android/repo/sys-img2/03" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <license id="$licencaId" type="text">$textoLicenca</license>
  <localPackage path="$($Pacote.path)" obsolete="false">$corpo</localPackage>
</ns2:repository>
"@
  $arquivo = Join-Path $Destino "package.xml"
  [System.IO.File]::WriteAllText($arquivo, $xml, (New-Object System.Text.UTF8Encoding $false))
  Write-Host "  package.xml escrito."
}

# ---------------------------------------------------------------- emulador

Write-Host "== Emulador =="
$docRepo = [xml](Invoke-WebRequest "$Base/repository2-3.xml" -UseBasicParsing).Content
# O repositório publica o emulador em mais de um canal. Preferimos o ESTÁVEL: a primeira versão do
# script pegava "o maior arquivo" e caía no build de preview sem perceber.
$candidatos = @($docRepo.'sdk-repository'.remotePackage | Where-Object { $_.path -eq 'emulator' })
$pkgEmu = $candidatos | Where-Object { $_.'uses-license'.ref -eq 'android-sdk-license' } | Select-Object -First 1
if (-not $pkgEmu) { $pkgEmu = $candidatos | Select-Object -First 1 }

$destinoEmu = Join-Path $SdkRoot "emulator"
if (Test-Path (Join-Path $destinoEmu "emulator.exe")) {
  Write-Host "  já instalado."
  # Se o emulador que está no disco veio de outro canal, o package.xml tem de descrever ELE, não o
  # que o script escolheria hoje — senão o avdmanager acredita numa versão que não está ali.
  $instalado = (Get-Content (Join-Path $destinoEmu "source.properties") -ErrorAction SilentlyContinue |
    Select-String '^Pkg.Revision=(.+)$').Matches.Groups[1].Value
  if ($instalado) {
    $mesmo = $candidatos | Where-Object {
      "$($_.revision.major).$($_.revision.minor).$($_.revision.micro)" -eq $instalado
    } | Select-Object -First 1
    if ($mesmo) { $pkgEmu = $mesmo }
  }
} else {
  $arq = Get-ArquivoWindows $pkgEmu
  $zip = Get-Pacote -Url "$Base/$($arq.complete.url)" -Sha1 (Get-Sha1 $arq.complete.checksum) `
                    -Nome $arq.complete.url -Bytes ([int64]$arq.complete.size)
  Expandir -Zip $zip -Destino $destinoEmu
}
Write-PackageXml -Pacote $pkgEmu -Doc $docRepo -Destino $destinoEmu

# ---------------------------------------------------------------- imagem de sistema

$caminho = "system-images;android-$ApiLevel;$Tag;$Abi"
Write-Host "== $caminho =="
$docImg = [xml](Invoke-WebRequest "$Base/sys-img/$Tag/sys-img2-3.xml" -UseBasicParsing).Content
$pkgImg = $docImg.'sdk-sys-img'.remotePackage | Where-Object { $_.path -eq $caminho } | Select-Object -First 1
if (-not $pkgImg) { throw "Imagem $caminho não existe no repositório." }

$destinoImg = Join-Path $SdkRoot "system-images\android-$ApiLevel\$Tag\$Abi"
if (Test-Path (Join-Path $destinoImg "system.img")) {
  Write-Host "  já instalada."
} else {
  $arq = $pkgImg.archives.archive | Select-Object -First 1
  # a url do archive é relativa à pasta do XML, não à raiz do repositório
  $zip = Get-Pacote -Url "$Base/sys-img/$Tag/$($arq.complete.url)" -Sha1 (Get-Sha1 $arq.complete.checksum) `
                    -Nome $arq.complete.url -Bytes ([int64]$arq.complete.size)
  Expandir -Zip $zip -Destino $destinoImg
}
Write-PackageXml -Pacote $pkgImg -Doc $docImg -Destino $destinoImg

Write-Host ""
Write-Host "Pronto. Próximo passo: scripts\emulador.ps1" -ForegroundColor Cyan
