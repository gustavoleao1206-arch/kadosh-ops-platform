<#
.SYNOPSIS
  Instala o NDK que o Flutter exige, sem passar pelo sdkmanager.

.DESCRIPTION
  O plugin do Flutter pede um NDK em toda build Android, mesmo num app sem código nativo, e tenta
  baixá-lo rodando `sdkmanager --install ndk;<versão>`. Nesta máquina a CLI do SDK inteira morre com
  0xC0000409. Mas o plugin checa antes se a versão já está instalada — e, se estiver, nem chama o
  sdkmanager. Então basta pôr o NDK no lugar certo.

  A URL sai do próprio repositório do Google, não de palpite.

.EXAMPLE
  scripts\instalar-ndk.ps1
#>
param(
  [string]$Versao = "28.2.13676358",
  [string]$SdkRoot = "X:\dev\tools\android-sdk"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-Sha1 {
  <#
    O <checksum> do repositorio vem com atributo type="sha1". Com atributo, o PowerShell devolve o
    XmlElement inteiro em vez do texto — e comparar isso com um hash nunca bate. Foi exatamente o
    que aconteceu na primeira execucao deste script.
  #>
  param($Checksum)
  if ($Checksum -is [System.Xml.XmlElement]) { return $Checksum.InnerText }
  return [string]$Checksum
}


$destino = Join-Path $SdkRoot "ndk\$Versao"
if (Test-Path (Join-Path $destino "source.properties")) {
  Write-Host "NDK $Versao já está instalado em $destino." -ForegroundColor Green
  exit 0
}

Write-Host "Procurando a URL oficial do NDK $Versao..."
$xml = [xml](Invoke-WebRequest -Uri "https://dl.google.com/android/repository/repository2-3.xml" -UseBasicParsing).Content
$pkg = $xml.'sdk-repository'.remotePackage | Where-Object { $_.path -eq "ndk;$Versao" }
if (-not $pkg) { Write-Error "NDK $Versao não existe no repositório do Google."; exit 1 }

$arq = $pkg.archives.archive | Where-Object { $_.'host-os' -eq 'windows' } | Select-Object -First 1
if (-not $arq) { Write-Error "Não há build de Windows para o NDK $Versao."; exit 1 }

$url = "https://dl.google.com/android/repository/$($arq.complete.url)"
$mb = [math]::Round([int64]$arq.complete.size / 1MB, 0)
Write-Host "Baixando $url ($mb MB)..."

$downloads = "X:\dev\downloads"
New-Item -ItemType Directory -Force $downloads | Out-Null
$zip = Join-Path $downloads $arq.complete.url
if (-not (Test-Path $zip)) {
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
}

# Confere o SHA-1 que o próprio repositório publica: 700 MB baixados pela metade viram um erro
# incompreensível lá na frente, dentro do Gradle.
Write-Host "Conferindo integridade..."
$sha = (Get-FileHash $zip -Algorithm SHA1).Hash.ToLower()
if ($sha -ne (Get-Sha1 $arq.complete.checksum).ToLower()) {
  Remove-Item $zip -Force
  Write-Error "Checksum não bateu. O download foi apagado; rode de novo."
  exit 1
}

$tmp = Join-Path $env:TEMP "ndk-$Versao"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Force $tmp | Out-Null

Write-Host "Extraindo..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $tmp)

# o zip vem com uma pasta única dentro (android-ndk-rXXy); o SDK espera o conteúdo dela em ndk/<versão>
$interno = Get-ChildItem $tmp -Directory | Select-Object -First 1
New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
Move-Item $interno.FullName $destino
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

Write-Host "NDK $Versao instalado em $destino." -ForegroundColor Green
Get-Content (Join-Path $destino "source.properties") | Select-String "Pkg.Revision"
