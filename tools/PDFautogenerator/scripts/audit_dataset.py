from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pdf_autogenerator.audit import audit_dataset  # noqa: E402
from pdf_autogenerator.audit_config import load_audit_config  # noqa: E402


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run strict dataset audit against a manifest")
    parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")
    parser.add_argument("--config", required=True, help="Path to audit YAML configuration")
    parser.add_argument("--output", required=False, help="Optional path for JSON audit report")
    args = parser.parse_args()

    report = audit_dataset(
        Path(args.manifest),
        load_audit_config(args.config),
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
