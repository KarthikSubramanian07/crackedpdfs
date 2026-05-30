#!/usr/bin/env bash
set -euo pipefail

python -m src.cli train --model logreg --config configs/model_logreg.yaml
python -m src.cli train --model xgb --config configs/model_xgb.yaml
