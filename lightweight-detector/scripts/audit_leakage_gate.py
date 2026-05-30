from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common import load_yaml_config, resolve_path
from src.data.build_splits import load_splits
from src.eval.run import _shortcut_feature_risks, _write_shortcut_audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic single-feature leakage gate without model baselines."
    )
    parser.add_argument("--config", default="configs/eval_hard_provenance_fast.yaml")
    parser.add_argument("--output", default="")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--fail-on-shortcut-risk", action="store_true")
    parser.add_argument(
        "--include-original-benign",
        action="store_true",
        help="Audit all labels, including unmatched original benign PDFs. By default, use the matched benign-confounder subset when present.",
    )
    args = parser.parse_args()

    config = load_yaml_config(args.config)
    leakage_gate = config.get("leakage_gate", {}) or {}
    threshold = float(
        args.threshold
        if args.threshold is not None
        else leakage_gate.get("single_feature_accuracy_threshold", 0.70)
    )
    output_path = (
        resolve_path(args.output)
        if args.output
        else resolve_path(config["artifacts_dir"]) / "metrics" / "shortcut_feature_audit.csv"
    )

    labels = pd.read_parquet(resolve_path(config["labels_path"]))
    features = pd.read_parquet(resolve_path(config["features_path"]))
    splits = load_splits(resolve_path(config["splits_path"]))
    merged = labels.merge(features, on="pdf_id", how="inner", validate="one_to_one")
    test_frame = merged[merged["pdf_id"].isin(splits["test_ids"])].copy().reset_index(drop=True)
    test_frame = _select_leakage_audit_frame(
        test_frame,
        include_original_benign=args.include_original_benign,
    )
    if test_frame.empty:
        raise SystemExit("Test split is empty; cannot audit leakage.")

    audit_path = _write_shortcut_audit(
        test_frame,
        test_frame["label"].astype(int).to_numpy(),
        output_path,
    )
    risks = _shortcut_feature_risks(audit_path, threshold=threshold)

    summary_path = _summary_path_for_audit(audit_path, explicit_output=bool(args.output))
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["threshold", "risky_feature_count", "top_risky_features", "passed"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "threshold": threshold,
                "risky_feature_count": len(risks),
                "top_risky_features": ";".join(str(item["feature"]) for item in risks[:10]),
                "passed": len(risks) == 0,
            }
        )

    print(audit_path)
    print(summary_path)
    if risks and (args.fail_on_shortcut_risk or bool(leakage_gate.get("fail_on_shortcut_risk", False))):
        risky = ", ".join(str(item["feature"]) for item in risks[:10])
        raise SystemExit(
            f"Leakage gate failed: trainable single-feature accuracy >= {threshold:.3f}: {risky}"
        )


def _select_leakage_audit_frame(
    frame: pd.DataFrame,
    *,
    include_original_benign: bool,
) -> pd.DataFrame:
    if include_original_benign or "pdf_role" not in frame.columns:
        return frame
    roles = frame["pdf_role"].astype(str)
    matched_subset = frame[roles.isin({"benign_confounder", "injected_attack"})].copy()
    if matched_subset.empty or matched_subset["label"].astype(int).nunique() < 2:
        return frame
    return matched_subset.reset_index(drop=True)


def _summary_path_for_audit(audit_path: Path, *, explicit_output: bool) -> Path:
    if not explicit_output:
        return audit_path.with_name("shortcut_feature_gate_summary.csv")
    stem = audit_path.stem
    if stem.endswith("_audit"):
        summary_stem = stem[: -len("_audit")] + "_gate_summary"
    elif "audit" in stem:
        summary_stem = stem.replace("audit", "gate_summary")
    else:
        summary_stem = stem + "_gate_summary"
    return audit_path.with_name(summary_stem + audit_path.suffix)


if __name__ == "__main__":
    main()
