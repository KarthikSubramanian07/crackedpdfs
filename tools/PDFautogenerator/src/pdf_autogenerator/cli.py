from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_dataset
from .audit_config import load_audit_config
from .config import load_config
from .generator import generate_documents
from .qa import run_qa
from .validation import validate_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benign one-page PDF autogenerator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate benign one-page PDFs")
    generate_parser.add_argument("--config", required=True, help="Path to YAML configuration")

    alias_parser = subparsers.add_parser("generate-base", help="Alias for generate")
    alias_parser.add_argument("--config", required=True, help="Path to YAML configuration")

    validate_parser = subparsers.add_parser("validate", help="Validate a manifest and its PDFs")
    validate_parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")

    qa_parser = subparsers.add_parser("qa", help="Run dataset QA checks against a manifest")
    qa_parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")
    qa_parser.add_argument("--config", required=False, help="Optional YAML config for profile-aware QA")

    audit_parser = subparsers.add_parser("audit", help="Run strict production dataset audit")
    audit_parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")
    audit_parser.add_argument("--config", required=True, help="Path to audit YAML configuration")
    audit_parser.add_argument("--output", required=False, help="Optional path for JSON audit report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"generate", "generate-base"}:
        config = load_config(args.config)
        rows = generate_documents(config)
        print(json.dumps({"generated_rows": len(rows), "manifest": str(config.manifest_path)}))
        return 0

    if args.command == "validate":
        valid, issues = validate_manifest(Path(args.manifest))
        print(json.dumps({"valid": valid, "issue_count": len(issues), "issues": issues}))
        return 0 if valid else 1

    if args.command == "qa":
        config = load_config(args.config) if args.config else None
        report = run_qa(Path(args.manifest), config=config)
        print(json.dumps(report, indent=2))
        return 0 if report["overall_pass"] else 1

    if args.command == "audit":
        audit_config = load_audit_config(args.config)
        report = audit_dataset(
            Path(args.manifest),
            audit_config,
            output_path=Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["overall_pass"] else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
