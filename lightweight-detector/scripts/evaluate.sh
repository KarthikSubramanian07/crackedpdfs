#!/usr/bin/env bash
set -euo pipefail

python -m src.cli evaluate --config configs/eval.yaml
