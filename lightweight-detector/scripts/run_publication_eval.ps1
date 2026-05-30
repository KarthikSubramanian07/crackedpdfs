param(
  [string]$DetectorRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$EvalConfig = "configs/eval_hard_provenance_publication.yaml",
  [string]$HoldoutManifest = "configs/holdout_attack_families/manifest.yaml",
  [string]$ArtifactManifest = "data/artifacts/publication/frozen_artifact_manifest.json",
  [double]$MinPairCoverage = 0.95,
  [double]$SingleFeatureThreshold = 0.70,
  [int]$FeatureWorkers = 8,
  [int]$HoldoutParallelJobs = 2,
  [switch]$SkipHoldoutTraining
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedPython {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

function Invoke-Stage {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [scriptblock]$Body
  )

  $stageStart = Get-Date
  Write-Output "[publication] phase=$Name started_at_utc=$($stageStart.ToUniversalTime().ToString("o"))"
  & $Body
  $elapsed = (Get-Date) - $stageStart
  Write-Output "[publication] phase=$Name done elapsed_seconds=$([Math]::Round($elapsed.TotalSeconds, 3))"
}

function Add-Artifact {
  param(
    [System.Collections.ArrayList]$Artifacts,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$Path,
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

Push-Location $DetectorRoot
try {
  $startedAt = (Get-Date).ToUniversalTime().ToString("o")
  $env:SOLVANCE_FEATURE_WORKERS = "$FeatureWorkers"
  Write-Output "[publication] config featureWorkers=$FeatureWorkers holdoutParallelJobs=$HoldoutParallelJobs skipHoldoutTraining=$SkipHoldoutTraining"

  Invoke-Stage "compile" {
    Invoke-CheckedPython @("-m", "compileall", "src", "scripts")
  }

  Invoke-Stage "generate-holdout-configs" {
    Invoke-CheckedPython @("scripts/generate_attack_family_holdout_configs.py")
  }

  Invoke-Stage "build-splits" {
    Invoke-CheckedPython @("-m", "src.cli", "build-splits", "--config", "configs/dataset_hard_provenance.yaml")
  }

  Invoke-Stage "validate" {
    Invoke-CheckedPython @("-m", "src.cli", "validate-dataset", "--config", "configs/dataset_hard_provenance.yaml")
  }

  Invoke-Stage "build-features" {
    Invoke-CheckedPython @("-m", "src.cli", "build-features", "--config", "configs/features_hard_provenance.yaml")
  }

  Invoke-Stage "train-primary-models" {
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "logreg", "--config", "configs/model_logreg_hard_provenance_shortcut_free.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "xgb", "--config", "configs/model_xgb_hard_provenance_shortcut_free.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "text", "--config", "configs/model_text_tfidf_hard_provenance.yaml")
    Invoke-CheckedPython @("-m", "src.cli", "train", "--model", "hybrid", "--config", "configs/model_hybrid_hard_provenance.yaml")
  }

  Invoke-Stage "evaluate-primary-with-rule-and-promptguard" {
    Invoke-CheckedPython @("-m", "src.cli", "evaluate", "--config", $EvalConfig)
  }

  if (-not $SkipHoldoutTraining) {
    $families = @(
      "steganographic_acrostic",
      "microglyph_steganography",
      "semantic_fragmentation",
      "layout_mimicry",
      "margin_microtext",
      "in_page_low_contrast_text"
    )
    $maxJobs = [Math]::Max(1, $HoldoutParallelJobs)
    $jobs = [System.Collections.ArrayList]::new()
    $repo = (Get-Item -LiteralPath ".").FullName

    foreach ($family in $families) {
      while (($jobs | Where-Object { $_.State -eq "Running" }).Count -ge $maxJobs) {
        $runningJobs = @($jobs | Where-Object { $_.State -eq "Running" })
        $finished = Wait-Job -Job $runningJobs -Any
        Receive-Job -Job $finished
        if ($finished.State -ne "Completed") {
          throw "holdout job failed for family=$($finished.Name) state=$($finished.State)"
        }
        [void]$jobs.Remove($finished)
        Remove-Job -Job $finished -Force
      }

      $job = Start-Job -Name $family -ArgumentList $repo, $family -ScriptBlock {
        param($Repo, $Family)
        $ErrorActionPreference = "Stop"
        Set-Location $Repo
        $datasetConfig = "configs/holdout_attack_families/dataset_$Family.yaml"
        $modelOnlyEvalConfig = "configs/holdout_attack_families/eval_model_only_$Family.yaml"
        $started = Get-Date
        Write-Output "[publication] phase=holdout family=$Family started_at_utc=$($started.ToUniversalTime().ToString("o"))"
        python -m src.cli validate-dataset --config $datasetConfig
        if ($LASTEXITCODE -ne 0) { throw "validate failed for $Family" }
        python -m src.cli build-splits --config $datasetConfig
        if ($LASTEXITCODE -ne 0) { throw "build-splits failed for $Family" }
        python -m src.cli train --model logreg --config "configs/holdout_attack_families/model_logreg_shortcut_free_$Family.yaml"
        if ($LASTEXITCODE -ne 0) { throw "train logreg failed for $Family" }
        python -m src.cli train --model xgb --config "configs/holdout_attack_families/model_xgb_shortcut_free_$Family.yaml"
        if ($LASTEXITCODE -ne 0) { throw "train xgb failed for $Family" }
        python -m src.cli train --model text --config "configs/holdout_attack_families/model_text_tfidf_$Family.yaml"
        if ($LASTEXITCODE -ne 0) { throw "train text failed for $Family" }
        python -m src.cli train --model hybrid --config "configs/holdout_attack_families/model_hybrid_$Family.yaml"
        if ($LASTEXITCODE -ne 0) { throw "train hybrid failed for $Family" }
        python -m src.cli evaluate --config $modelOnlyEvalConfig
        if ($LASTEXITCODE -ne 0) { throw "evaluate failed for $Family" }
        $elapsed = (Get-Date) - $started
        Write-Output "[publication] phase=holdout family=$Family done elapsed_seconds=$([Math]::Round($elapsed.TotalSeconds, 3))"
      }
      [void]$jobs.Add($job)
    }

    if ($jobs.Count -gt 0) {
      Wait-Job -Job $jobs | Out-Null
      foreach ($job in $jobs) {
        Receive-Job -Job $job
        if ($job.State -ne "Completed") {
          throw "holdout job failed for family=$($job.Name) state=$($job.State)"
        }
      }
      Remove-Job -Job $jobs -Force
    }
  }

  Invoke-Stage "pairing-audit" {
    Invoke-CheckedPython @(
      "scripts/audit_counterfactual_pairing.py",
      "--manifest", $HoldoutManifest,
      "--min-coverage", "$MinPairCoverage",
      "--fail-under-min"
    )
  }

  Invoke-Stage "leakage-gate" {
    Invoke-CheckedPython @(
      "scripts/audit_leakage_gate.py",
      "--config", $EvalConfig,
      "--threshold", "$SingleFeatureThreshold",
      "--fail-on-shortcut-risk"
    )
  }

  Invoke-Stage "aggregate-holdouts" {
    Invoke-CheckedPython @("scripts/aggregate_holdout_attack_family_results.py", "--manifest", $HoldoutManifest)
  }

  Invoke-Stage "frozen-manifest" {
    $artifacts = [System.Collections.ArrayList]::new()
    $artifactCandidates = [ordered]@{
      eval_config = $EvalConfig
      dataset_config = "configs/dataset_hard_provenance.yaml"
      features_config = "configs/features_hard_provenance.yaml"
      holdout_manifest = $HoldoutManifest
      raw_metadata = "data/raw/metadata.jsonl"
      run_metadata = "data/raw/metadata.json"
      processed_features = "data/processed/hard_provenance/features.parquet"
      processed_labels = "data/processed/hard_provenance/labels.parquet"
      processed_splits = "data/processed/hard_provenance/splits.json"
      feature_schema = "data/artifacts/hard_provenance/feature_schema.json"
      logreg_model = "data/artifacts/hard_provenance/models/logreg_shortcut_free.pkl"
      xgb_model = "data/artifacts/hard_provenance/models/xgb_shortcut_free.pkl"
      text_tfidf_model = "data/artifacts/hard_provenance/models/text_tfidf.pkl"
      hybrid_model = "data/artifacts/hard_provenance/models/hybrid.pkl"
      promptguard_scores = "data/artifacts/hard_provenance_publication/metrics/promptguard_scores.csv"
      publication_metrics = "data/artifacts/hard_provenance_publication/metrics/metrics.json"
      pairing_audit = "data/artifacts/holdout_attack_family/counterfactual_pairing_audit.csv"
      aggregate_metrics = "data/artifacts/holdout_attack_family/aggregate_metrics.csv"
      target_family_metrics = "data/artifacts/holdout_attack_family/target_family_focus_metrics.csv"
      matched_counterfactual_metrics = "data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv"
      leakage_audit = "data/artifacts/hard_provenance_publication/metrics/shortcut_feature_audit.csv"
      leakage_gate_summary = "data/artifacts/hard_provenance_publication/metrics/shortcut_feature_gate_summary.csv"
    }
    foreach ($entry in $artifactCandidates.GetEnumerator()) {
      Add-Artifact -Artifacts $artifacts -Name $entry.Key -Path $entry.Value
    }

    $manifestDir = Split-Path -Parent $ArtifactManifest
    if (-not [string]::IsNullOrWhiteSpace($manifestDir)) {
      New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
    }
    $payload = [ordered]@{
      frozen_at_utc = (Get-Date).ToUniversalTime().ToString("o")
      started_at_utc = $startedAt
      detector_root = (Get-Item -LiteralPath ".").FullName
      note = "Frozen after local publication eval. This script intentionally does not generate the 10k corpus."
      feature_workers = $FeatureWorkers
      holdout_parallel_jobs = $HoldoutParallelJobs
      artifacts = $artifacts
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ArtifactManifest -Encoding utf8
    Write-Output $ArtifactManifest
  }
} finally {
  Pop-Location
}

Write-Output "[publication] done"
