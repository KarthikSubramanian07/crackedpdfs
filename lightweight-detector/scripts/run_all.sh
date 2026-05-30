#!/usr/bin/env bash
set -euo pipefail

python -m src.cli validate-dataset --config configs/dataset.yaml
python -m src.cli build-features --config configs/features.yaml
python -m src.cli build-splits --config configs/dataset.yaml
python -m src.cli train --model logreg --config configs/model_logreg.yaml
python -m src.cli train --model xgb --config configs/model_xgb.yaml
python -m src.cli evaluate --config configs/eval.yaml
