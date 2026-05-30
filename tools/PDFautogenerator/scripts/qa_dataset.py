from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pdf_autogenerator.qa import run_qa  # noqa: E402


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run dataset QA checks against a manifest")
    parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")
    parser.add_argument("--config", required=False, help="Optional YAML config for profile-aware QA")
    args = parser.parse_args()

    from pdf_autogenerator.config import load_config  # noqa: E402

    config = load_config(args.config) if args.config else None
    report = run_qa(Path(args.manifest), config=config)
    print(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
