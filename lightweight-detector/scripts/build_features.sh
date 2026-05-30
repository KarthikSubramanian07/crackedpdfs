#!/usr/bin/env bash
set -euo pipefail

python -m src.cli build-features --config configs/features.yaml
