param(
  [string]$DetectorRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$EvalConfig = "configs/eval_publication_final.yaml",
  [string]$HoldoutManifest = "configs/holdout_attack_families/manifest.yaml",
  [string]$ArtifactManifest = "data/artifacts/publication_final/frozen_artifact_manifest.json",
  [double]$MinPairCoverage = 0.99,
  [double]$SingleFeatureThreshold = 0.70,
  [int]$FeatureWorkers = 8,
  [switch]$SkipHoldoutTraining
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedPython {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  Write-Output "[publication-final] python_start args=$($Arguments -join ' ')"
  $previousErrorAction = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    python @Arguments
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
  Write-Output "[publication-final] python_done exit_code=$exitCode args=$($Arguments -join ' ')"
  if ($exitCode -ne 0) {
    throw "python $($Arguments -join ' ') failed with exit code $exitCode"
  }
}

function Invoke-Stage {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][scriptblock]$Body
  )
  $stageStart = Get-Date
  Write-Output "[publication-final] phase=$Name started_at_utc=$($stageStart.ToUniversalTime().ToString("o"))"
  & $Body
  $elapsed = (Get-Date) - $stageStart
  Write-Output "[publication-final] phase=$Name done elapsed_seconds=$([Math]::Round($elapsed.TotalSeconds, 3))"
}

function Invoke-GitCapture {
  param(
    [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$ErrorPath
  )
  if ([string]::IsNullOrWhiteSpace($ErrorPath)) {
    $ErrorPath = "$OutputPath.stderr.txt"
  }
  $previousErrorAction = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & git @Arguments > $OutputPath 2> $ErrorPath
    if ($LASTEXITCODE -ne 0) {
      throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
}

function Add-Artifact {
  param(
    [System.Collections.ArrayList]$Artifacts,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Path,
    [bool]$Required = $true
  )
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    if ($Required) {
      throw "required publication artifact missing: $Name at $Path"
    }
    return
  }
  $item = Get-Item -LiteralPath $Path
  $hash = Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256
  [void]$Artifacts.Add([ordered]@{
    name = $Name
    path = $item.FullName
    sha256 = $hash.Hash.ToLowerInvariant()
    bytes = $item.Length
    last_write_time_utc = $item.LastWriteTimeUtc.ToString("o")
  })
}

function New-SourceSnapshot {
  param(
    [Parameter(Mandatory = $true)][string]$OutputPath
  )

  $tracked = @{}
  git ls-files | ForEach-Object {
    if (-not [string]::IsNullOrWhiteSpace($_)) {
      $tracked[$_.Replace("\", "/")] = $true
    }
  }

  $roots = @("configs", "scripts", "src")
  $rootFiles = @("README.md", "requirements.txt", "pyproject.toml", "setup.cfg", "setup.py")
  $extensions = @(".json", ".md", ".ps1", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml")
  $files = [System.Collections.ArrayList]::new()

  foreach ($root in $roots) {
    if (Test-Path -LiteralPath $root -PathType Container) {
      Get-ChildItem -LiteralPath $root -Recurse -File |
        Where-Object {
          $_.FullName -notmatch "\\__pycache__\\" -and
          $_.FullName -notmatch "\\.pytest_cache\\" -and
          $_.Extension.ToLowerInvariant() -in $extensions
        } |
        ForEach-Object { [void]$files.Add($_) }
    }
  }

  foreach ($file in $rootFiles) {
    if (Test-Path -LiteralPath $file -PathType Leaf) {
      [void]$files.Add((Get-Item -LiteralPath $file))
    }
  }

  $entries = [System.Collections.ArrayList]::new()
  $repoRoot = (Get-Item -LiteralPath ".").FullName.TrimEnd("\", "/")
  foreach ($file in ($files | Sort-Object FullName -Unique)) {
    $relativePath = $file.FullName.Substring($repoRoot.Length).TrimStart("\", "/").Replace("\", "/")
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    [void]$entries.Add([ordered]@{
      path = $relativePath
      sha256 = $hash.Hash.ToLowerInvariant()
      bytes = $file.Length
      last_write_time_utc = $file.LastWriteTimeUtc.ToString("o")
      tracked_by_git = $tracked.ContainsKey($relativePath)
    })
  }

  $status = @(git status --short)
  $head = (git rev-parse HEAD).Trim()
  $payload = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    git_head = $head
    git_status_short = $status
    scope = "Hashes for source/config/script/dependency files needed to identify a dirty publication run."
    file_count = $entries.Count
    files = $entries
  }

  $outDir = Split-Path -Parent $OutputPath
  if (-not [string]::IsNullOrWhiteSpace($outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  }
  $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
  return $payload
}

Push-Location $DetectorRoot
try {
  $startedAt = (Get-Date).ToUniversalTime().ToString("o")
  $env:SOLVANCE_FEATURE_WORKERS = "$FeatureWorkers"

  Invoke-Stage "compile" {
    Invoke-CheckedPython @("-m", "compileall", "src", "scripts")
  }

  Invoke-Stage "environment-freeze" {
    New-Item -ItemType Directory -Force -Path "data/artifacts/publication_final/reproducibility" | Out-Null
    python --version | Set-Content -LiteralPath "data/artifacts/publication_final/reproducibility/python_version.txt" -Encoding utf8
    python -m pip freeze | Set-Content -LiteralPath "data/artifacts/publication_final/reproducibility/pip_freeze.txt" -Encoding utf8
    Invoke-GitCapture @("rev-parse", "HEAD") "data/artifacts/publication_final/reproducibility/git_head.txt"
    Invoke-GitCapture @("status", "--short") "data/artifacts/publication_final/reproducibility/git_status_short.txt"
    Invoke-GitCapture @("diff", "--stat") "data/artifacts/publication_final/reproducibility/git_diff_stat.txt" "data/artifacts/publication_final/reproducibility/git_diff_stat.stderr.txt"
    Invoke-GitCapture @("diff", "--binary") "data/artifacts/publication_final/reproducibility/git_diff.patch" "data/artifacts/publication_final/reproducibility/git_diff.stderr.txt"
    Invoke-GitCapture @("diff", "--cached", "--binary") "data/artifacts/publication_final/reproducibility/git_diff_cached.patch" "data/artifacts/publication_final/reproducibility/git_diff_cached.stderr.txt"
    Invoke-GitCapture @("ls-files", "--others", "--exclude-standard") "data/artifacts/publication_final/reproducibility/git_untracked_files.txt"
  }

  Invoke-Stage "generate-holdout-configs" {
    Invoke-CheckedPython @("scripts/generate_attack_family_holdout_configs.py")
  }

  Invoke-Stage "validate-build-splits-features" {
    Invoke-CheckedPython @("-m", "src.cli", "validate-dataset", "--config", "configs/dataset_hard_provenance.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "build-splits", "--config", "configs/dataset_hard_provenance.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "build-features", "--config", "configs/features_hard_provenance.yaml")
  }

  Invoke-Stage "train-primary-models" {
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "logreg", "--config", "configs/model_logreg_hard_provenance_shortcut_free.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "xgb", "--config", "configs/model_xgb_hard_provenance_shortcut_free.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "text", "--config", "configs/model_text_tfidf_hard_provenance.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "hybrid", "--config", "configs/model_hybrid_hard_provenance.yaml")
  }

  Invoke-Stage "evaluate-final" {
    Invoke-CheckedPython @("-m", "src.cli", "evaluate", "--config", $EvalConfig)
  }

  if (-not $SkipHoldoutTraining) {
    Invoke-Stage "holdout-family-models" {
      Invoke-CheckedPython @("scripts/generate_attack_family_holdout_configs.py")
      $families = @(
        "steganographic_acrostic",
        "microglyph_steganography",
        "semantic_fragmentation",
        "layout_mimicry",
        "margin_microtext",
        "in_page_low_contrast_text"
      )
      foreach ($family in $families) {
        Invoke-CheckedPython @("-m", "src.cli", "validate-dataset", "--config", "configs/holdout_attack_families/dataset_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "build-splits", "--config", "configs/holdout_attack_families/dataset_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "logreg", "--config", "configs/holdout_attack_families/model_logreg_shortcut_free_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "xgb", "--config", "configs/holdout_attack_families/model_xgb_shortcut_free_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "text", "--config", "configs/holdout_attack_families/model_text_tfidf_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "hybrid", "--config", "configs/holdout_attack_families/model_hybrid_$family.yaml")
        Invoke-CheckedPython @("-m", "src.cli", "evaluate", "--config", "configs/holdout_attack_families/eval_model_only_$family.yaml")
      }
    }
  }

  Invoke-Stage "audits" {
    Invoke-CheckedPython @("scripts/audit_counterfactual_pairing.py", "--manifest", $HoldoutManifest, "--min-coverage", "$MinPairCoverage", "--fail-under-min")
    Invoke-CheckedPython @("scripts/audit_leakage_gate.py", "--config", $EvalConfig, "--threshold", "$SingleFeatureThreshold", "--fail-on-shortcut-risk")
    Invoke-CheckedPython @("scripts/audit_leakage_gate.py", "--config", $EvalConfig, "--output", "data/artifacts/publication_final/metrics/shortcut_feature_audit_full_test.csv", "--threshold", "$SingleFeatureThreshold", "--include-original-benign", "--fail-on-shortcut-risk")
    Invoke-CheckedPython @("scripts/aggregate_holdout_attack_family_results.py", "--manifest", $HoldoutManifest)
    Invoke-CheckedPython @("scripts/check_publication_readiness.py", "--config", $EvalConfig, "--metrics", "data/artifacts/publication_final/metrics/metrics.json", "--require-bootstrap", "--require-ablations", "--require-sanity")
  }

  Invoke-Stage "frozen-manifest" {
    $sourceSnapshotPath = "data/artifacts/publication_final/reproducibility/source_file_hashes.json"
    $sourceSnapshot = New-SourceSnapshot -OutputPath $sourceSnapshotPath
    $artifacts = [System.Collections.ArrayList]::new()
    $artifactCandidates = [ordered]@{
      eval_config = $EvalConfig
      requirements = "requirements.txt"
      dataset_config = "configs/dataset_hard_provenance.yaml"
      features_config = "configs/features_hard_provenance.yaml"
      holdout_manifest = $HoldoutManifest
      raw_metadata_jsonl = "data/raw/metadata.jsonl"
      raw_metadata_json = "data/raw/metadata.json"
      processed_features = "data/processed/hard_provenance/features.parquet"
      processed_labels = "data/processed/hard_provenance/labels.parquet"
      processed_splits = "data/processed/hard_provenance/splits.json"
      feature_schema = "data/artifacts/hard_provenance/feature_schema.json"
      logreg_model = "data/artifacts/hard_provenance/models/logreg_shortcut_free.pkl"
      xgb_model = "data/artifacts/hard_provenance/models/xgb_shortcut_free.pkl"
      text_tfidf_model = "data/artifacts/hard_provenance/models/text_tfidf.pkl"
      hybrid_model = "data/artifacts/hard_provenance/models/hybrid.pkl"
      final_metrics = "data/artifacts/publication_final/metrics/metrics.json"
      final_hard_setting_summary = "data/artifacts/publication_final/metrics/hard_setting_summary.csv"
      final_ablations = "data/artifacts/publication_final/metrics/ablations.csv"
      final_leakage_audit = "data/artifacts/publication_final/metrics/shortcut_feature_audit.csv"
      final_leakage_gate_summary = "data/artifacts/publication_final/metrics/shortcut_feature_gate_summary.csv"
      final_leakage_audit_full_test = "data/artifacts/publication_final/metrics/shortcut_feature_audit_full_test.csv"
      final_leakage_gate_summary_full_test = "data/artifacts/publication_final/metrics/shortcut_feature_gate_summary_full_test.csv"
      promptguard_scores = "data/artifacts/hard_provenance_publication/metrics/promptguard_scores.csv"
      pairing_audit = "data/artifacts/holdout_attack_family/counterfactual_pairing_audit.csv"
      aggregate_metrics = "data/artifacts/holdout_attack_family/aggregate_metrics.csv"
      target_family_metrics = "data/artifacts/holdout_attack_family/target_family_focus_metrics.csv"
      matched_counterfactual_metrics = "data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv"
      python_version = "data/artifacts/publication_final/reproducibility/python_version.txt"
      pip_freeze = "data/artifacts/publication_final/reproducibility/pip_freeze.txt"
      git_head = "data/artifacts/publication_final/reproducibility/git_head.txt"
      git_status = "data/artifacts/publication_final/reproducibility/git_status_short.txt"
      git_diff_stat = "data/artifacts/publication_final/reproducibility/git_diff_stat.txt"
      git_diff_stat_stderr = "data/artifacts/publication_final/reproducibility/git_diff_stat.stderr.txt"
      git_diff_patch = "data/artifacts/publication_final/reproducibility/git_diff.patch"
      git_diff_stderr = "data/artifacts/publication_final/reproducibility/git_diff.stderr.txt"
      git_diff_cached_patch = "data/artifacts/publication_final/reproducibility/git_diff_cached.patch"
      git_diff_cached_stderr = "data/artifacts/publication_final/reproducibility/git_diff_cached.stderr.txt"
      git_untracked_files = "data/artifacts/publication_final/reproducibility/git_untracked_files.txt"
      source_file_hashes = $sourceSnapshotPath
    }
    foreach ($entry in $artifactCandidates.GetEnumerator()) {
      Add-Artifact -Artifacts $artifacts -Name $entry.Key -Path $entry.Value
    }
    $manifestDir = Split-Path -Parent $ArtifactManifest
    if ($manifestDir) {
      New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
    }
    [ordered]@{
      frozen_at_utc = (Get-Date).ToUniversalTime().ToString("o")
      started_at_utc = $startedAt
      detector_root = (Get-Item -LiteralPath ".").FullName
      claim_scope = "Controlled hard-provenance benchmark plus sanitized hybrid text/structure detector; structural-only results are negative controls."
      source_snapshot = $sourceSnapshot
      artifacts = $artifacts
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ArtifactManifest -Encoding utf8
    Write-Output $ArtifactManifest
  }
} catch {
  Write-Output "[publication-final] fatal=$($_.Exception.Message)"
  Write-Output "[publication-final] fatal_record=$($_ | Out-String)"
  exit 1
} finally {
  Pop-Location
}

Write-Output "[publication-final] done"
