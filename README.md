# crackedpdfs

`crackedpdfs` is a reproducible backend experiment stack for building and evaluating a controlled PDF prompt-injection benchmark.

The repository contains the code needed to generate fresh benign PDFs, create injected and matched benign-confounder PDF variants, export detector-ready metadata, train lightweight detectors, and run publication-style evaluations. It intentionally does not include old generated PDFs, old model artifacts, cached outputs, local databases, logs, virtual environments, `node_modules`, or secrets.

## Research Goal

Document-based LLM systems often flatten PDFs before guardrails inspect them. That flattening step can remove evidence that a prompt-injection instruction was hidden from the human reader but still visible to a parser or extractor. This project tests whether PDF-level structure and sanitized extracted text can detect controlled hidden prompt injections before document content reaches an LLM pipeline.

The intended claim is narrow. This repository supports controlled benchmark experiments. It should not be used to claim broad real-world robustness against all PDFs, all parser pipelines, all OCR systems, or fully adaptive attackers without additional evaluation.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `tools/PDFautogenerator/` | Deterministic benign one-page PDF generator. |
| `src/backend/services/dataset-mode/` | Backend dataset creation engine for grouped, paired benchmark samples. |
| `src/backend/services/processing/layers/02-watermarking/volks-pdf-blocker-ada-layer-1/` | PDF content-stream injection engine and validation helpers. |
| `src/lib/prompt-injection-message-library.ts` | Prompt-injection message library used by the benchmark engine. |
| `src/lib/prompt-injection-taxonomy.ts` | Message-type taxonomy. |
| `src/lib/pdf-benchmark-taxonomy.ts` | PDF attack-family and regime taxonomy. |
| `lightweight-detector/` | Feature extraction, splitting, training, baselines, audits, metrics, and publication evaluation. |
| `scripts/run_crackedpdfs_experiment.ps1` | Main one-command experiment runner. |
| `drizzle/` | Database migrations for the local experiment database. |
| `storage/` | Local backend database and generated benchmark files. This directory is kept empty in Git except for placeholders. |
| `generated/` | Fresh benign PDF generation output. This directory is created at runtime and ignored by Git. |

## What Is Generated Locally

The following paths are runtime outputs and are ignored by Git:

| Path | Contents |
| --- | --- |
| `generated/` | Fresh benign source PDFs from `PDFautogenerator`. |
| `storage/` | Local SQLite/libSQL database and backend-created benchmark files. |
| `lightweight-detector/data/raw/` | Exported detector corpus and metadata. |
| `lightweight-detector/data/processed/` | Feature tables, grouped splits, and schemas. |
| `lightweight-detector/data/artifacts/` | Trained models, metrics, plots, audit reports, and publication manifests. |
| `.venv/` | Local Python virtual environment. |
| `node_modules/` | Local Node dependencies. |

## Prerequisites

Use Windows PowerShell from the repository root.

Required:

- Git.
- Node.js with `npm`.
- Python 3.11 or newer. Python 3.13 was used during recent local validation.
- PowerShell.

Recommended for the full publication run:

- A machine that can stay awake for a long-running experiment.
- Enough free disk space for generated PDFs and detector artifacts.
- Hugging Face authentication with access to PromptGuard if you want the PromptGuard baseline.

The smoke run does not require Hugging Face authentication.

## Fresh Clone Setup

Clone the repository:

```powershell
git clone https://github.com/volkthienpreecha/crackedpdfs.git
cd crackedpdfs
```

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

The default `.env.example` uses a local file-backed SQLite/libSQL database:

```text
TURSO_CONNECTION_URL=file:./storage/crackedpdfs.db
TURSO_AUTH_TOKEN=
HF_TOKEN=
```

You normally do not need to change this for local reproduction.

## Hugging Face and PromptGuard

PromptGuard is used as a text-only baseline. It should be run on extracted natural-language text, not on raw PDF object syntax. The rule baseline and learned structural detectors are responsible for PDF-structure-aware detection.

For full publication evaluation with PromptGuard, authenticate with Hugging Face:

```powershell
hf auth login
```

If you prefer token-based configuration, set `HF_TOKEN` in `.env`.

PromptGuard access can require accepting the model terms on Hugging Face. If PromptGuard authentication or access is not configured, the rest of the benchmark can still be generated and evaluated, but the PromptGuard baseline may fail or be skipped depending on the local environment.

## Quick Smoke Run

Run the smoke experiment first:

```powershell
npm run experiment:smoke
```

The smoke run is designed to verify that the complete local pipeline works on a small fresh corpus. It performs these steps:

1. Installs Node dependencies with `npm install`.
2. Creates a local Python virtual environment at `.venv/`.
3. Installs the local PDF generator into the virtual environment.
4. Installs lightweight detector Python dependencies.
5. Creates or updates the local database schema with Drizzle.
6. Generates a small fresh benign PDF corpus.
7. Runs backend dataset-mode injection with matched benign confounders.
8. Exports detector-ready files and metadata.
9. Validates the dataset.
10. Builds grouped splits and features.
11. Trains structural, text-only, and hybrid detector models.
12. Runs model-only evaluation.

After the first successful setup, you can skip dependency installation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_crackedpdfs_experiment.ps1 -Mode smoke -SkipInstall
```

You can also run a smaller diagnostic smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_crackedpdfs_experiment.ps1 -Mode smoke -GeneratedCount 24 -TargetSamples 12 -Concurrency 4 -FeatureWorkers 2
```

## Full Publication-Style Run

Run the full experiment:

```powershell
npm run experiment:publication
```

This run is more expensive than the smoke test. It generates a fresh 10,000-document source corpus and then executes the publication evaluation path.

The publication run performs these steps:

1. Generates 10,000 fresh benign source PDFs.
2. Creates paired benign originals, matched benign confounders, and injected PDFs.
3. Enforces paired coverage constraints in the backend dataset engine.
4. Exports canonical detector metadata and PDF paths.
5. Validates metadata, pair coverage, and leakage-sensitive fields.
6. Builds hard-provenance grouped splits.
7. Extracts PDF structural features and sanitized extracted-text features.
8. Trains structural-only, text-only, and hybrid detector models.
9. Runs the rule baseline.
10. Runs PromptGuard on extracted text if Hugging Face access is configured.
11. Runs label-shuffle sanity checks.
12. Runs shortcut and leakage audits.
13. Runs held-out attack-family stress tests.
14. Writes publication metrics, subgroup reports, plots, and frozen reproducibility manifests.

Expected output roots:

```text
generated/benign-<runId>/
storage/tenants/tenant-demo/users/tenant-demo/<runId>/
lightweight-detector/data/raw/
lightweight-detector/data/processed/
lightweight-detector/data/artifacts/
```

## Runner Options

The main runner is `scripts/run_crackedpdfs_experiment.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_crackedpdfs_experiment.ps1 -Mode smoke
```

Available options:

| Option | Default | Description |
| --- | --- | --- |
| `-Mode smoke` | `smoke` | Runs a small end-to-end validation pipeline. |
| `-Mode publication` | `smoke` | Runs the full publication-style experiment. |
| `-RunId <value>` | Timestamped ID | Controls output directory names and dataset identifiers. |
| `-GeneratedCount <n>` | `96` for smoke, `10000` for publication | Number of benign source PDFs to generate. |
| `-TargetSamples <n>` | `48` for smoke, `10000` for publication | Target number of backend benchmark samples. |
| `-GeneratorSeed <n>` | `20260525` | Seed for benign PDF generation. |
| `-BenchmarkSeed <n>` | `20260525` | Seed for benchmark sample assignment. |
| `-Concurrency <n>` | `8` | Backend dataset creation concurrency. |
| `-FeatureWorkers <n>` | `4` | Detector feature extraction workers. |
| `-SkipInstall` | Off | Skips dependency installation after the first successful setup. |

## Important Artifact Files

After a full publication-style run, the main files to inspect are:

```text
lightweight-detector/data/artifacts/publication_final/metrics/metrics.json
lightweight-detector/data/artifacts/publication_final/metrics/hard_setting_summary.csv
lightweight-detector/data/artifacts/publication_final/metrics/shortcut_feature_audit.csv
lightweight-detector/data/artifacts/publication_final/claim_scope_report.md
lightweight-detector/data/artifacts/publication_final/frozen_artifact_manifest.json
lightweight-detector/data/artifacts/holdout_attack_family/aggregate_metrics.csv
lightweight-detector/data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv
lightweight-detector/data/artifacts/hard_provenance_publication/metrics/promptguard_scores.csv
```

The exact artifact set can vary if PromptGuard is unavailable or if an evaluation stage is intentionally skipped.

## Evaluation Design

The benchmark uses grouped splitting by base PDF identity. Derived samples from the same base document should not cross train, validation, and test boundaries. This is intended to reduce leakage from base-document memorization.

The dataset engine supports multiple PDF hiding and attack-family regimes. It also supports paired matched confounders, where a target injected sample is compared against a benign sample that shares non-label provenance features. This makes the evaluation harder than a simple benign-versus-injected split.

The detector side includes:

- Rule-based PDF structural baseline.
- PromptGuard extracted-text baseline.
- Structural-only learned detector.
- Text-only learned detector over sanitized extracted text.
- Hybrid detector over sanitized text and PDF structure.
- Label-shuffle controls.
- Shortcut and leakage audits.
- Held-out attack-family stress tests.
- Subgroup reporting by message type, attack family, and regime metadata.

## Interpreting Results

High scores on this benchmark should be interpreted as evidence that controlled PDF prompt injections leave detectable redundant traces under the tested regimes. They should not be interpreted as a guarantee of robustness to arbitrary real-world PDFs, OCR-only pipelines, unseen parsers, adaptive attacks, or all future hiding methods.

For paper claims, use paired and leakage-audited results first. Avoid emphasizing raw perfect or near-perfect accuracy without the controls and limitations.

## Troubleshooting

If PowerShell blocks script execution, run commands with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_crackedpdfs_experiment.ps1 -Mode smoke
```

If Node dependencies are missing, run:

```powershell
npm install
```

If the local database schema is missing or stale, run:

```powershell
npx drizzle-kit push
```

If Python dependencies fail, confirm that `python --version` reports Python 3.11 or newer, then rerun the smoke command without `-SkipInstall`.

If PromptGuard fails, confirm that Hugging Face authentication is configured and that the account has access to the PromptGuard model. The smoke run is the fastest way to verify the rest of the stack without PromptGuard.

## Git Hygiene

Do not commit generated datasets, PDFs, local databases, trained models, metrics outputs, `.env`, `.venv`, or `node_modules`. The repository is configured to ignore those paths so the public repo remains source-only and reproducible from a fresh run.

## License and Citation

This repository contains experiment code and bundled open-source font assets with their own license files. If you use this repository in a paper or derivative benchmark, cite the repository and cite the external prompt-injection datasets, PromptGuard model, and font sources used by your run.
