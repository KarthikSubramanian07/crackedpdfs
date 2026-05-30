param(
  [string]$DetectorRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$ArtifactManifest = "data/artifacts/publication_final/frozen_artifact_manifest.json"
)

$ErrorActionPreference = "Stop"
$PythonBin = if ([string]::IsNullOrWhiteSpace($env:PYTHON_BIN)) { "python" } else { $env:PYTHON_BIN }

function Write-JsonFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][object]$Value,
    [int]$Depth = 8
  )
  $json = $Value | ConvertTo-Json -Depth $Depth
  $encoding = [System.Text.UTF8Encoding]::new($false)
  $resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location) $Path }
  [System.IO.File]::WriteAllText($resolvedPath, $json, $encoding)
}

function Convert-TextFileToUtf8NoBom {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return
  }
  $content = Get-Content -LiteralPath $Path -Raw
  $encoding = [System.Text.UTF8Encoding]::new($false)
  $resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location) $Path }
  [System.IO.File]::WriteAllText($resolvedPath, $content, $encoding)
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

function Invoke-GitCapture {
  param(
    [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$ErrorPath
  )
  if ([string]::IsNullOrWhiteSpace($ErrorPath)) {
    $ErrorPath = "$OutputPath.stderr.txt"
  }
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & git @Arguments > $OutputPath 2> $ErrorPath
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

function Invoke-CommandCapture {
  param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$ErrorPath
  )
  if ([string]::IsNullOrWhiteSpace($ErrorPath)) {
    $ErrorPath = "$OutputPath.stderr.txt"
  }
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Executable @Arguments > $OutputPath 2> $ErrorPath
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($LASTEXITCODE -ne 0) {
    throw "$Executable $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
  Convert-TextFileToUtf8NoBom -Path $OutputPath
  Convert-TextFileToUtf8NoBom -Path $ErrorPath
}

function New-SourceSnapshot {
  param([string]$OutputPath)
  $roots = @("src", "scripts", "configs")
  $rootFiles = @("README.md", "requirements.txt", "pyproject.toml")
  $rows = [System.Collections.ArrayList]::new()
  foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) {
      continue
    }
    Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object {
      $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
      [void]$rows.Add([ordered]@{
        path = (Resolve-Path -LiteralPath $_.FullName -Relative).Replace("\\", "/")
        sha256 = $hash.Hash.ToLowerInvariant()
        bytes = $_.Length
        last_write_time_utc = $_.LastWriteTimeUtc.ToString("o")
      })
    }
  }
  foreach ($file in $rootFiles) {
    if (Test-Path -LiteralPath $file -PathType Leaf) {
      $item = Get-Item -LiteralPath $file
      $hash = Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256
      [void]$rows.Add([ordered]@{
        path = $file
        sha256 = $hash.Hash.ToLowerInvariant()
        bytes = $item.Length
        last_write_time_utc = $item.LastWriteTimeUtc.ToString("o")
      })
    }
  }
  Write-JsonFile -Path $OutputPath -Value $rows -Depth 6
  return $rows
}

Push-Location $DetectorRoot
try {
  $reproDir = "data/artifacts/publication_final/reproducibility"
  New-Item -ItemType Directory -Force -Path $reproDir | Out-Null
  & $PythonBin --version | Set-Content -LiteralPath "$reproDir/python_version.txt" -Encoding utf8
  & $PythonBin -m pip freeze | Set-Content -LiteralPath "$reproDir/pip_freeze.txt" -Encoding utf8
  Invoke-GitCapture @("rev-parse", "HEAD") "$reproDir/git_head.txt"
  Invoke-GitCapture @("status", "--short") "$reproDir/git_status_short.txt"
  Invoke-GitCapture @("diff", "--stat") "$reproDir/git_diff_stat.txt" "$reproDir/git_diff_stat.stderr.txt"
  Invoke-GitCapture @("diff", "--binary") "$reproDir/git_diff.patch" "$reproDir/git_diff.stderr.txt"
  Invoke-GitCapture @("diff", "--cached", "--binary") "$reproDir/git_diff_cached.patch" "$reproDir/git_diff_cached.stderr.txt"
  Invoke-GitCapture @("ls-files", "--others", "--exclude-standard") "$reproDir/git_untracked_files.txt"
  Invoke-CommandCapture $PythonBin @("scripts/repair_publication_repro_bundle.py", "--config", "configs/eval_publication_final.yaml", "--metrics", "data/artifacts/publication_final/metrics/metrics.json") "$reproDir/repro_bundle_repair.json" "$reproDir/repro_bundle_repair.stderr.txt"
  Invoke-CommandCapture $PythonBin @("scripts/check_publication_readiness.py", "--config", "configs/eval_publication_final.yaml", "--metrics", "data/artifacts/publication_final/metrics/metrics.json", "--require-bootstrap", "--require-ablations", "--require-sanity") "$reproDir/publication_readiness.json" "$reproDir/publication_readiness.stderr.txt"
  Invoke-CommandCapture $PythonBin @("scripts/write_publication_claim_scope.py", "--metrics", "data/artifacts/publication_final/metrics/metrics.json", "--matched-counterfactual", "data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv", "--output", "data/artifacts/publication_final/claim_scope_report.md", "--json-output", "data/artifacts/publication_final/claim_scope_report.json") "$reproDir/claim_scope_report_command.stdout.txt" "$reproDir/claim_scope_report_command.stderr.txt"
  $sourceSnapshotPath = "$reproDir/source_file_hashes.json"
  $sourceSnapshot = New-SourceSnapshot -OutputPath $sourceSnapshotPath

  $artifacts = [System.Collections.ArrayList]::new()
  $artifactCandidates = [ordered]@{
    eval_config = "configs/eval_publication_final.yaml"
    requirements = "requirements.txt"
    dataset_config = "configs/dataset_hard_provenance.yaml"
    features_config = "configs/features_hard_provenance.yaml"
    holdout_manifest = "configs/holdout_attack_families/manifest.yaml"
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
    claim_scope_report = "data/artifacts/publication_final/claim_scope_report.md"
    claim_scope_report_json = "data/artifacts/publication_final/claim_scope_report.json"
    promptguard_scores = "data/artifacts/hard_provenance_publication/metrics/promptguard_scores.csv"
    pairing_audit = "data/artifacts/holdout_attack_family/counterfactual_pairing_audit.csv"
    aggregate_metrics = "data/artifacts/holdout_attack_family/aggregate_metrics.csv"
    target_family_metrics = "data/artifacts/holdout_attack_family/target_family_focus_metrics.csv"
    matched_counterfactual_metrics = "data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv"
    python_version = "$reproDir/python_version.txt"
    pip_freeze = "$reproDir/pip_freeze.txt"
    git_head = "$reproDir/git_head.txt"
    git_status = "$reproDir/git_status_short.txt"
    git_diff_stat = "$reproDir/git_diff_stat.txt"
    git_diff_stat_stderr = "$reproDir/git_diff_stat.stderr.txt"
    git_diff_patch = "$reproDir/git_diff.patch"
    git_diff_stderr = "$reproDir/git_diff.stderr.txt"
    git_diff_cached_patch = "$reproDir/git_diff_cached.patch"
    git_diff_cached_stderr = "$reproDir/git_diff_cached.stderr.txt"
    git_untracked_files = "$reproDir/git_untracked_files.txt"
    repro_bundle_repair = "$reproDir/repro_bundle_repair.json"
    repro_bundle_repair_stderr = "$reproDir/repro_bundle_repair.stderr.txt"
    publication_readiness = "$reproDir/publication_readiness.json"
    publication_readiness_stderr = "$reproDir/publication_readiness.stderr.txt"
    claim_scope_report_command_stdout = "$reproDir/claim_scope_report_command.stdout.txt"
    claim_scope_report_command_stderr = "$reproDir/claim_scope_report_command.stderr.txt"
    source_file_hashes = $sourceSnapshotPath
  }
  foreach ($entry in $artifactCandidates.GetEnumerator()) {
    Add-Artifact -Artifacts $artifacts -Name $entry.Key -Path $entry.Value
  }
  $manifestDir = Split-Path -Parent $ArtifactManifest
  if ($manifestDir) {
    New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
  }
  $manifest = [ordered]@{
    frozen_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    detector_root = (Get-Item -LiteralPath ".").FullName
    claim_scope = "Controlled hard-provenance benchmark plus sanitized hybrid text/structure detector; structural-only results are negative controls."
    source_snapshot = $sourceSnapshot
    artifacts = $artifacts
  }
  Write-JsonFile -Path $ArtifactManifest -Value $manifest -Depth 8
  Write-Output $ArtifactManifest
} finally {
  Pop-Location
}
