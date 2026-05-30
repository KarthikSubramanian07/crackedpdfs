param(
  [ValidateSet("smoke", "publication")]
  [string]$Mode = "smoke",
  [string]$RunId = "",
  [int]$GeneratedCount = 0,
  [int]$TargetSamples = 0,
  [int]$GeneratorSeed = 20260525,
  [int]$BenchmarkSeed = 20260525,
  [int]$Concurrency = 8,
  [int]$FeatureWorkers = 4,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

function Read-DotEnv {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return
  }
  Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if ($line.Length -eq 0 -or $line.StartsWith("#")) {
      return
    }
    $parts = $line.Split("=", 2)
    if ($parts.Count -eq 2) {
      [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
  }
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string[]]$Arguments
  )
  Write-Output "[crackedpdfs] run $Command $($Arguments -join ' ')"
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$generatorRoot = Join-Path $repoRoot "tools\PDFautogenerator"
$detectorRoot = Join-Path $repoRoot "lightweight-detector"
$venvRoot = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($RunId)) {
  $RunId = "crackedpdfs-$Mode-$(Get-Date -Format yyyyMMdd-HHmmss)"
}
if ($GeneratedCount -le 0) {
  $GeneratedCount = if ($Mode -eq "publication") { 10000 } else { 96 }
}
if ($TargetSamples -le 0) {
  $TargetSamples = if ($Mode -eq "publication") { 10000 } else { 48 }
}

$envPath = Join-Path $repoRoot ".env"
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
  Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination $envPath
}
Read-DotEnv -Path $envPath

$sourceRoot = Join-Path $repoRoot "generated\benign-$RunId"
$generatorConfig = Join-Path $generatorRoot "configs\generated_$RunId.yaml"
$sourceManifest = Join-Path $sourceRoot "manifest.jsonl"

if (-not $SkipInstall) {
  Push-Location $repoRoot
  try {
    Invoke-Checked "npm.cmd" @("install")
  } finally {
    Pop-Location
  }

  if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Invoke-Checked "python" @("-m", "venv", $venvRoot)
  }
  Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Checked $venvPython @("-m", "pip", "install", "-e", $generatorRoot)
  Invoke-Checked $venvPython @("-m", "pip", "install", "-r", (Join-Path $detectorRoot "requirements.txt"))
}

$pythonCommand = if (Test-Path -LiteralPath $venvPython -PathType Leaf) { $venvPython } else { "python" }

Push-Location $repoRoot
try {
  Invoke-Checked "npx.cmd" @("drizzle-kit", "push")
} finally {
  Pop-Location
}

$yaml = @"
output_root: "$($sourceRoot.Replace('\', '/'))"
total_count: $GeneratedCount
seed: $GeneratorSeed
resume_mode: overwrite

family_weights:
  academic_handout: 1.0
  business_memo_report: 1.0
  form_worksheet: 1.0
  policy_notice: 1.0
  invoice_receipt: 1.0
  syllabus_info: 1.0

template_allowlist: []

page_size_weights:
  letter: 1.0
  a4: 1.0

margin_presets:
  - 0.5in
  - 0.75in
  - 1.0in

density_presets:
  - sparse
  - normal
  - dense

font_allowlist:
  - source_serif_4
  - source_sans_3
  - libre_baskerville
  - liberation_serif
  - liberation_sans

header_probability: 0.72
footer_probability: 0.56
small_text_probability: 0.34
table_region_probability: 0.8
"@
Set-Content -LiteralPath $generatorConfig -Value $yaml -Encoding utf8

Push-Location $generatorRoot
try {
  Invoke-Checked $pythonCommand @("-m", "pdf_autogenerator.cli", "generate", "--config", $generatorConfig)
  Invoke-Checked $pythonCommand @("-m", "pdf_autogenerator.cli", "validate", "--manifest", $sourceManifest)
} finally {
  Pop-Location
}

$env:BENCHMARK_SOURCE_ROOT = $sourceRoot
$env:BENCHMARK_RUN_ID = $RunId
$env:BENCHMARK_SOURCE_RUN_ID = $RunId
$env:BENCHMARK_DATASET_NAME = $RunId
$env:BENCHMARK_SEED = "$BenchmarkSeed"
$env:BENCHMARK_TARGET_SAMPLES = "$TargetSamples"
$env:BENCHMARK_PROCESSING_CONCURRENCY = "$Concurrency"
$env:BENCHMARK_MATCHED_CONFOUNDERS = "true"
$env:BENCHMARK_MIN_PAIR_COVERAGE = "0.95"
$env:WATERMARK_LAYER_ROOT = Join-Path $repoRoot "src\backend\services\processing\layers\02-watermarking"
$env:ADA_LAYER_SCRIPT_PATH = Join-Path $env:WATERMARK_LAYER_ROOT "volks-pdf-blocker-ada-layer-1\inject_policy.py"
$env:ADA_LAYER_VALIDATION_HARNESS_PATH = Join-Path $env:WATERMARK_LAYER_ROOT "volks-pdf-blocker-ada-layer-1\validation_harness.py"
$env:ADA_LAYER_POLICY_TEXT_PATH = Join-Path $env:WATERMARK_LAYER_ROOT "volks-pdf-blocker-ada-layer-1\instruction_override.txt"
$env:PYTHON_BIN = $pythonCommand

Push-Location $repoRoot
try {
  Invoke-Checked "npx.cmd" @("--yes", "tsx", "scripts/run_pdf_benchmark_10k.ts")
} finally {
  Pop-Location
}

Push-Location $detectorRoot
try {
  $env:SOLVANCE_FEATURE_WORKERS = "$FeatureWorkers"
  if ($Mode -eq "publication") {
    Invoke-Checked "powershell.exe" @("-ExecutionPolicy", "Bypass", "-File", "scripts\run_publication_final.ps1", "-FeatureWorkers", "$FeatureWorkers")
    Invoke-Checked "powershell.exe" @("-ExecutionPolicy", "Bypass", "-File", "scripts\freeze_publication_manifest.ps1")
  } else {
    Invoke-Checked $pythonCommand @("-m", "src.cli", "validate-dataset", "--config", "configs/dataset_hard_provenance.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "build-splits", "--config", "configs/dataset_hard_provenance.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "build-features", "--config", "configs/features_hard_provenance.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "train", "--model", "logreg", "--config", "configs/model_logreg_hard_provenance_shortcut_free.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "train", "--model", "xgb", "--config", "configs/model_xgb_hard_provenance_shortcut_free.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "train", "--model", "text", "--config", "configs/model_text_tfidf_hard_provenance.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "train", "--model", "hybrid", "--config", "configs/model_hybrid_hard_provenance.yaml")
    Invoke-Checked $pythonCommand @("-m", "src.cli", "evaluate", "--config", "configs/eval_hard_provenance_model_only.yaml")
  }
} finally {
  Pop-Location
}

Write-Output "[crackedpdfs] done mode=$Mode runId=$RunId"
