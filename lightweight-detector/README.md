# Solvance Detector

Reproducible document-level detector pipeline for structural prompt injection in PDFs (<= 2000>)

## Task

Binary classification:

- `0 = benign`
- `1 = injected`

This project is designed so you can drop a dataset into `data/raw/`, run one command, and get:

- canonicalized metadata
- validated dataset summaries
- fixed-schema PDF features with page-size normalization and leakage guards
- grouped train/val/test splits
- logistic regression and XGBoost baselines
- global metrics, per-regime metrics, ablations, sanity checks, and plots
- trained model artifacts and inference entrypoints

## Layout

```text
lightweight-detector/
|-- configs/
|-- data/
|   |-- raw/
|   |-- processed/
|   `-- artifacts/
|-- scripts/
`-- src/
```

## Supported Raw Dataset Layouts

### Canonical layout

```text
data/raw/
|-- pdfs/
`-- metadata.jsonl
```

Each JSONL row should contain at least:

```json
{
  "pdf_id": "doc_00123.injected",
  "base_pdf_id": "base_00045",
  "file_path": "pdfs/doc_00123.injected.pdf",
  "label": 1,
  "source_type": "academic",
  "spatial_regime": "near_margin",
  "rendering_regime": "white_text",
  "structural_regime": "inject_into_existing_stream",
  "message_type": "instruction_override",
  "artifact_wrapper": false,
  "seed": 42,
  "freeze_version": "freeze-2026-02-12",
  "split_group": "base_00045"
}
```

### Current sample-pair layout

The loader also supports your existing dataset export shape:

```text
data/raw/
|-- benign/
|-- injected/
|-- metadata/
|   `-- sample_0001.metadata.json
`-- metadata.json
```

That format is normalized into canonical rows automatically.

## Install

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

### PromptGuard access

The PromptGuard baseline uses Meta's gated Hugging Face model.

Recommended setup:

```bash
hf auth login
```

Or provide a token through environment variables:

```bash
$env:HF_TOKEN="hf_..."
```

The evaluation config defaults to:

```text
meta-llama/Prompt-Guard-86M
```

If the baseline cannot load the model, the evaluator will now raise a direct auth/setup error instead of a generic Transformers failure.

## Run

Full pipeline:

```bash
python -m src.cli run-all
```

Stepwise:

```bash
python -m src.cli validate-dataset --config configs/dataset.yaml
python -m src.cli build-features --config configs/features.yaml
python -m src.cli build-splits --config configs/dataset.yaml
python -m src.cli train --model logreg --config configs/model_logreg.yaml
python -m src.cli train --model xgb --config configs/model_xgb.yaml
python -m src.cli evaluate --config configs/eval.yaml
```

Inference:

```bash
python -m src.cli infer --model data/artifacts/models/xgb.pkl --pdf path/to/file.pdf
```

## Experimental Protocol

1. Validate dataset.
2. Canonicalize metadata.
3. Build fixed-schema features.
4. Freeze grouped splits by `base_pdf_id`.
5. Train logistic regression.
6. Train XGBoost.
7. Evaluate global metrics.
8. Evaluate per-regime metrics.
9. Run feature-group ablations.
10. Save all artifacts.

## Guardrails

- Metadata-only columns such as `base_pdf_id`, regime tags, `artifact_wrapper`, and `source_type` stay out of training features.
- Grouped splits are built by `base_pdf_id`.
- Evaluation saves misclassifications, label-shuffle sanity checks, and feature-group ablations.
- The validator warns about sparse regimes, source-type leakage, and split coverage gaps.

## Outputs

- Models: `data/artifacts/models/`
- Metrics: `data/artifacts/metrics/`
- Plots: `data/artifacts/plots/`
- Logs: `data/artifacts/logs/`
- Processed tables: `data/processed/`
