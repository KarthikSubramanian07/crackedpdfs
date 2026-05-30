# crackedpdfs

Reproducible backend experiment stack for the PDF prompt-injection benchmark used in the USENIX draft.

This repository is a clean runnable copy of the experiment code. It intentionally does **not** include old generated PDFs, old detector outputs, cached models, logs, or local secrets. A coauthor should be able to start from this repository, generate fresh benign PDFs, inject prompt-injection variants through the backend dataset engine, train/evaluate the detector, and reproduce the publication-style artifact structure.

## What Is Included

- `tools/PDFautogenerator/` — deterministic benign one-page PDF generator.
- `src/backend/services/dataset-mode/` — backend dataset-mode engine for paired benign/injected/confounder generation.
- `src/backend/services/processing/layers/02-watermarking/volks-pdf-blocker-ada-layer-1/` — PDF content-stream injection engine.
- `src/lib/prompt-injection-message-library.ts` — local prompt-injection message library.
- `src/lib/prompt-injection-taxonomy.ts` — message-type taxonomy.
- `src/lib/pdf-benchmark-taxonomy.ts` — PDF attack-family taxonomy.
- `lightweight-detector/` — ML feature extraction, training, baselines, audits, and publication evaluation.
- `scripts/run_crackedpdfs_experiment.ps1` — one-command smoke or publication run.

## What Is Excluded

- `generated/` fresh benign PDF outputs.
- `storage/` backend-generated datasets.
- `lightweight-detector/data/raw/` exported detector corpus.
- `lightweight-detector/data/processed/` feature tables and splits.
- `lightweight-detector/data/artifacts/` models, metrics, plots, and manifests.
- `.env` secrets.
- `node_modules/`, Python virtualenvs, caches, and logs.

These paths are generated locally and ignored by Git.

## Setup

Requirements:

- Windows PowerShell.
- Node.js with `npm`.
- Python 3.11+; Python 3.13 was used during development.
- Hugging Face authentication if running the full publication evaluation with PromptGuard.

Create your local env file:

```powershell
Copy-Item .env.example .env
```

The default `.env.example` uses a local SQLite/libSQL database:

```text
TURSO_CONNECTION_URL=file:./storage/crackedpdfs.db
TURSO_AUTH_TOKEN=
```

For PromptGuard, authenticate separately:

```powershell
hf auth login
```

## Quick Smoke Run

This verifies the end-to-end backend path on a small fresh corpus.

```powershell
npm run experiment:smoke
```

The smoke run:

1. Installs Node dependencies and creates a local Python `.venv`.
2. Creates/updates the local DB schema.
3. Generates a small benign PDF corpus.
4. Runs backend dataset-mode injection with matched benign confounders.
5. Exports detector-ready raw data under `lightweight-detector/data/raw/`.
6. Builds features and splits.
7. Trains structural, text, and hybrid models.
8. Runs model-only evaluation.

To skip dependency installation after the first run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_crackedpdfs_experiment.ps1 -Mode smoke -SkipInstall
```

## Full Publication-Style Run

This is the expensive run. It generates a fresh 10k source corpus and executes the publication pipeline.

```powershell
npm run experiment:publication
```

The full run:

1. Generates 10,000 benign source PDFs.
2. Uses the backend to create paired benign originals, matched benign confounders, and injected PDFs.
3. Exports canonical detector metadata and PDFs.
4. Builds hard-provenance features and grouped splits.
5. Trains structural-only, text-only, and hybrid models.
6. Runs PromptGuard as extracted-text baseline.
7. Runs rule baseline, ablations, label-shuffle sanity checks, leakage audits, and held-out attack-family stress tests.
8. Freezes publication artifacts and a reproducibility manifest.

Expected output roots:

- `generated/benign-<runId>/`
- `storage/tenants/tenant-demo/users/tenant-demo/<runId>/`
- `lightweight-detector/data/raw/`
- `lightweight-detector/data/processed/`
- `lightweight-detector/data/artifacts/`

## Main Publication Artifacts

After a full run, the important files are:

- `lightweight-detector/data/artifacts/publication_final/metrics/metrics.json`
- `lightweight-detector/data/artifacts/publication_final/metrics/hard_setting_summary.csv`
- `lightweight-detector/data/artifacts/publication_final/metrics/shortcut_feature_audit.csv`
- `lightweight-detector/data/artifacts/publication_final/claim_scope_report.md`
- `lightweight-detector/data/artifacts/publication_final/frozen_artifact_manifest.json`
- `lightweight-detector/data/artifacts/holdout_attack_family/aggregate_metrics.csv`
- `lightweight-detector/data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv`
- `lightweight-detector/data/artifacts/hard_provenance_publication/metrics/promptguard_scores.csv`

## Claim Scope

The intended claim is narrow:

> On a controlled hard-provenance PDF prompt-injection benchmark with paired benign confounders and leakage audits, a sanitized hybrid text/structure detector performs strongly while text-only and structural-only baselines expose limitations.

Do not claim broad real-world robustness or reliable generalization to all unseen attack families from this repository alone.
