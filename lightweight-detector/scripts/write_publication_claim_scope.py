from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a conservative publication claim-scope report.")
    parser.add_argument("--metrics", default="data/artifacts/publication_final/metrics/metrics.json")
    parser.add_argument(
        "--matched-counterfactual",
        default="data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv",
    )
    parser.add_argument("--output", default="data/artifacts/publication_final/claim_scope_report.md")
    parser.add_argument("--json-output", default="data/artifacts/publication_final/claim_scope_report.json")
    return parser.parse_args()


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _model_snapshot(metrics: dict[str, Any], model_name: str) -> dict[str, Any]:
    payload = metrics.get("models", {}).get(model_name, {})
    model_metrics = payload.get("metrics", {})
    paired = payload.get("balanced_evaluation", {}).get("injected_vs_benign_confounder", {})
    ci = payload.get("confidence_intervals", {}).get("metrics", {}).get("f1", {})
    return {
        "f1": model_metrics.get("f1"),
        "roc_auc": model_metrics.get("roc_auc"),
        "pr_auc": model_metrics.get("pr_auc"),
        "accuracy": model_metrics.get("accuracy"),
        "paired_counterfactual_accuracy": paired.get("accuracy"),
        "paired_counterfactual_f1": paired.get("f1"),
        "paired_counterfactual_support": paired.get("support"),
        "f1_ci95_low": ci.get("ci95_low"),
        "f1_ci95_high": ci.get("ci95_high"),
    }


def main() -> None:
    args = parse_args()
    metrics_path = Path(args.metrics)
    matched_path = Path(args.matched_counterfactual)
    output_path = Path(args.output)
    json_output_path = Path(args.json_output)

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    matched_rows = _load_rows(matched_path)
    hybrid_rows = [row for row in matched_rows if row.get("method") == "hybrid"]
    unstable_hybrid_rows = []
    for row in hybrid_rows:
        accuracy = _float(row.get("accuracy"))
        roc_auc = _float(row.get("roc_auc"))
        paired_rank_accuracy = _float(row.get("paired_rank_accuracy"))
        if (
            accuracy is not None
            and accuracy < 0.75
            or roc_auc is not None
            and roc_auc < 0.75
            or paired_rank_accuracy is not None
            and paired_rank_accuracy < 0.75
        ):
            unstable_hybrid_rows.append(row)

    hybrid_pair_rank_values = [
        value
        for value in (_float(row.get("paired_rank_accuracy")) for row in hybrid_rows)
        if value is not None
    ]
    text_audit = metrics.get("models", {}).get("text_tfidf", {}).get("text_shortcut_audit", {})
    if not text_audit:
        text_audit = metrics.get("models", {}).get("text_tfidf", {}).get("shortcut_text_audit", {})
    if not text_audit:
        text_audit = metrics.get("models", {}).get("text_tfidf", {}).get("feature_weight_audit", {})

    report = {
        "claim_status": "narrow_claim_ready_with_caveats",
        "approved_primary_claim": (
            "On the controlled hard-provenance benchmark, the sanitized hybrid text/structure detector "
            "substantially outperforms PromptGuard and structural-only negative controls under paired "
            "benign-confounder evaluation, with explicit shortcut audits and label-shuffle sanity checks."
        ),
        "disallowed_strong_claims": [
            "Do not claim broad real-world PDF prompt-injection robustness.",
            "Do not claim reliable generalization across all held-out attack families.",
            "Do not present text_tfidf as clean positive evidence; treat it as a shortcut-prone comparator.",
            "Do not present structural-only logreg/xgb as strong detectors; frame them as negative controls.",
        ],
        "primary_model": "hybrid",
        "primary_metrics": _model_snapshot(metrics, "hybrid"),
        "text_tfidf_metrics": _model_snapshot(metrics, "text_tfidf"),
        "structural_negative_controls": {
            "logreg_shortcut_free": _model_snapshot(metrics, "logreg_shortcut_free"),
            "xgb_shortcut_free": _model_snapshot(metrics, "xgb_shortcut_free"),
        },
        "matched_counterfactual_hybrid_summary": {
            "families": len(hybrid_rows),
            "mean_paired_rank_accuracy": mean(hybrid_pair_rank_values) if hybrid_pair_rank_values else None,
            "unstable_family_rows": [
                {
                    "family": row.get("family"),
                    "accuracy": _float(row.get("accuracy")),
                    "roc_auc": _float(row.get("roc_auc")),
                    "paired_rank_accuracy": _float(row.get("paired_rank_accuracy")),
                }
                for row in unstable_hybrid_rows
            ],
        },
        "readiness_status": metrics.get("claim_readiness", {}),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Publication Claim Scope",
        "",
        "## Approved Primary Claim",
        "",
        report["approved_primary_claim"],
        "",
        "## Disallowed Strong Claims",
        "",
    ]
    lines.extend(f"- {item}" for item in report["disallowed_strong_claims"])
    lines.extend(
        [
            "",
            "## Primary Hybrid Result",
            "",
            f"- F1: {report['primary_metrics']['f1']}",
            f"- ROC-AUC: {report['primary_metrics']['roc_auc']}",
            f"- PR-AUC: {report['primary_metrics']['pr_auc']}",
            f"- Paired benign-confounder accuracy: {report['primary_metrics']['paired_counterfactual_accuracy']}",
            f"- Paired benign-confounder support: {report['primary_metrics']['paired_counterfactual_support']}",
            "",
            "## Matched Counterfactual Limitation",
            "",
            (
                "Held-out family matched-counterfactual results are reported as stress-test/limitation evidence, "
                "not as the main claim."
            ),
        ]
    )
    for row in report["matched_counterfactual_hybrid_summary"]["unstable_family_rows"]:
        lines.append(
            "- "
            f"{row['family']}: accuracy={row['accuracy']}, roc_auc={row['roc_auc']}, "
            f"paired_rank_accuracy={row['paired_rank_accuracy']}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
