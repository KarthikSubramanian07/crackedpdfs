# Paper environment

## Captured runtime

| Component | Version |
| --- | --- |
| Python | 3.13.7 |
| NumPy | 2.1.3 |
| pandas | 2.3.3 |
| PyArrow | 22.0.0 |
| pikepdf | 10.0.2 |
| pypdf | 6.4.0 |
| pdfplumber | 0.11.7 |
| PyMuPDF | 1.26.6 |
| scikit-learn | 1.8.0 |
| XGBoost | 3.2.0 |
| matplotlib | 3.10.8 |
| PyYAML | 6.0.3 |
| transformers | 4.57.1 |
| PyTorch | 2.6.0+cu124 |

The full environment is in [`reproducibility/pip-freeze.txt`](reproducibility/pip-freeze.txt). The original Python version capture is in [`reproducibility/python-version.txt`](reproducibility/python-version.txt).

## Platform capture

The run manifest and paths show that the paper evaluation ran on Windows from PowerShell. The exact Windows edition, build number, CPU, GPU, Node.js version, and npm version were not captured in the frozen bundle.

Do not infer those versions from a current developer machine. They are unknown for the paper run.

## Frozen configuration

The exact copied configurations are under [`reproducibility/configs/`](reproducibility/configs/):

- `dataset.yaml`;
- `eval.yaml`;
- `feature-schema.json`;
- `model-hybrid.yaml`;
- `model-logreg-shortcut-free.yaml`;
- `model-text-tfidf.yaml`; and
- `model-xgb-shortcut-free.yaml`.

## Recorded evaluation commands

The original manifest records these detector commands:

```text
python -m src.cli validate-dataset --config configs/dataset_hard_provenance.yaml
python -m src.cli build-splits --config configs/dataset_hard_provenance.yaml
python -m src.cli build-features --config configs/features_hard_provenance.yaml
python -m src.cli train --model logreg --config configs/model_logreg_hard_provenance_shortcut_free.yaml
python -m src.cli train --model xgb --config configs/model_xgb_hard_provenance_shortcut_free.yaml
python -m src.cli train --model text --config configs/model_text_tfidf_hard_provenance.yaml
python -m src.cli train --model hybrid --config configs/model_hybrid_hard_provenance.yaml
python -m src.cli evaluate --config configs/eval_publication_final.yaml
```

These commands expect feature, label, and PDF artifacts that are not committed in `paper-v1/`. They are provenance, not a complete fast reproduction command.
