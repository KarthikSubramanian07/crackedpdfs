[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[setup] $Message"
}

function Resolve-FileName {
    param([string]$Url)
    $clean = ($Url -split '\?')[0]
    return [System.IO.Path]::GetFileName($clean)
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$thirdParty = Join-Path $repoRoot "third_party"
$binDir = Join-Path $repoRoot "src\backend\services\processing\layers\02-watermarking\confusion-matrix-layer\binaries"
$libtorchDir = Join-Path $thirdParty "libtorch"
$libtorchSentinel = Join-Path $libtorchDir "lib\torch_cpu.dll"
$pdfiumSentinel = Join-Path $binDir "pdfium.dll"
$pdfiumWorkDir = Join-Path $thirdParty "pdfium-windows"

New-Item -ItemType Directory -Force -Path $thirdParty | Out-Null
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$defaultLibTorchUrl = "https://download.pytorch.org/libtorch/cu121/libtorch-win-shared-with-deps-2.3.0.zip"
$defaultPdfiumUrl = "https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/6666/pdfium-win-x64.tgz"

$libtorchUrl = if ($env:LIBTORCH_URL) { $env:LIBTORCH_URL } else { $defaultLibTorchUrl }
$pdfiumUrl = if ($env:PDFIUM_URL) { $env:PDFIUM_URL } else { $defaultPdfiumUrl }
$libtorchArchive = Join-Path $thirdParty (Resolve-FileName $libtorchUrl)
$pdfiumArchive = Join-Path $thirdParty (Resolve-FileName $pdfiumUrl)

function Download-File {
    param(
        [string]$Url,
        [string]$Destination
    )

    if (-not $Force.IsPresent -and (Test-Path $Destination)) {
        Write-Info "Using cached $(Split-Path $Destination -Leaf)"
        return
    }

    Write-Info "Downloading $(Split-Path $Destination -Leaf)"
    $temp = "$Destination.partial"
    Remove-Item -Force $temp -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $Url -OutFile $temp
    Move-Item -Force $temp $Destination
}

function Verify-Checksum {
    param(
        [string]$FilePath,
        [string]$Expected
    )

    if (-not $Expected) {
        return
    }

    $actual = (Get-FileHash -Algorithm SHA256 -Path $FilePath).Hash.ToLower()
    if ($actual -ne $Expected.ToLower()) {
        throw "Checksum mismatch for $FilePath.`nExpected: $Expected`nActual:   $actual"
    }
}

function Install-LibTorch {
    if (-not $Force.IsPresent -and (Test-Path $libtorchSentinel)) {
        Write-Info "libtorch already installed at $libtorchDir"
        return
    }

    Download-File -Url $libtorchUrl -Destination $libtorchArchive
    Verify-Checksum -FilePath $libtorchArchive -Expected $env:LIBTORCH_SHA256

    Write-Info "Extracting libtorch..."
    Remove-Item -Recurse -Force $libtorchDir -ErrorAction SilentlyContinue
    Expand-Archive -Path $libtorchArchive -DestinationPath $thirdParty -Force
}

function Install-Pdfium {
    if (-not $Force.IsPresent -and (Test-Path $pdfiumSentinel)) {
        Write-Info "Pdfium already available at $pdfiumSentinel"
        return
    }

    if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
        throw "tar.exe is required to extract pdfium-win-x64.tgz. Install the Windows tar utility (Windows 10+ includes it)."
    }

    Download-File -Url $pdfiumUrl -Destination $pdfiumArchive
    Verify-Checksum -FilePath $pdfiumArchive -Expected $env:PDFIUM_SHA256

    Write-Info "Extracting Pdfium..."
    Remove-Item -Recurse -Force $pdfiumWorkDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $pdfiumWorkDir | Out-Null
    tar -xzf $pdfiumArchive -C $pdfiumWorkDir

    $dllPath = Join-Path $pdfiumWorkDir "bin\\pdfium.dll"
    if (-not (Test-Path $dllPath)) {
        throw "Pdfium archive did not contain pdfium.dll at $dllPath"
    }

    Copy-Item -Path $dllPath -Destination $pdfiumSentinel -Force
    Write-Info "Pdfium library placed at $pdfiumSentinel"
}

Install-LibTorch
Install-Pdfium

Write-Info "Native dependencies ready."
Write-Info "Set LIBTORCH=$libtorchDir (e.g. in .env) so the Rust layer can locate libtorch."
