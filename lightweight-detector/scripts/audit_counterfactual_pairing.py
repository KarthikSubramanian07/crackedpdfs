from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aggregate_holdout_attack_family_results import MATCHED_CONFOUNDER_FAMILY
from src.common import load_yaml_config, resolve_path
from src.data.build_splits import load_splits


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit true counterfactual triad pairing coverage.")
    parser.add_argument("--manifest", default="configs/holdout_attack_families/manifest.yaml")
    parser.add_argument("--output", default="data/artifacts/holdout_attack_family/counterfactual_pairing_audit.csv")
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--fail-under-min", action="store_true")
    args = parser.parse_args()

    manifest = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in manifest["holdouts"]:
        family = str(item["attack_family"])
        confounder = MATCHED_CONFOUNDER_FAMILY.get(family)
        if not confounder:
            raise ValueError(f"No matched confounder family configured for {family}")

        eval_config = load_yaml_config(item.get("model_only_eval_config") or item["eval_config"])
        labels = pd.read_parquet(resolve_path(eval_config["labels_path"]))
        splits = load_splits(resolve_path(eval_config["splits_path"]))
        test = labels[labels["pdf_id"].isin(splits["test_ids"])].copy()

        target = test[(test["label"].astype(int) == 1) & (test["attack_family"].astype(str) == family)]
        matched = test[
            (test["label"].astype(int) == 0)
            & (test["benign_confounder_family"].astype(str) == confounder)
        ]

        group_column = "triad_id" if "triad_id" in test.columns else "pair_id" if "pair_id" in test.columns else "base_pdf_id"
        target_groups = set(target[group_column].astype(str))
        matched_groups = set(matched[group_column].astype(str))
        paired_groups = target_groups & matched_groups
        physical_columns = [
            ("target_physical_attack_family", "confounder_physical_attack_family"),
            ("target_physical_attack_strength", "confounder_physical_attack_strength"),
            ("target_physical_spatial_regime", "confounder_physical_spatial_regime"),
            ("target_physical_rendering_regime", "confounder_physical_rendering_regime"),
            ("target_physical_structural_regime", "confounder_physical_structural_regime"),
            ("target_physical_artifact_wrapper", "confounder_physical_artifact_wrapper"),
        ]
        available_physical_columns = [
            pair for pair in physical_columns if pair[0] in test.columns and pair[1] in test.columns
        ]
        physically_matched_groups = 0
        mismatched_physical_groups: list[str] = []
        for group_id in sorted(paired_groups):
            target_row = target[target[group_column].astype(str) == group_id].head(1)
            matched_row = matched[matched[group_column].astype(str) == group_id].head(1)
            if target_row.empty or matched_row.empty:
                continue
            group_matches = True
            for target_column, confounder_column in available_physical_columns:
                left = str(target_row.iloc[0][target_column])
                right = str(matched_row.iloc[0][confounder_column])
                if left != right:
                    group_matches = False
                    break
            if group_matches:
                physically_matched_groups += 1
            else:
                mismatched_physical_groups.append(group_id)
        coverage = len(paired_groups) / max(len(target_groups), 1)
        physical_coverage = physically_matched_groups / max(len(target_groups), 1)
        rows.append(
            {
                "attack_family": family,
                "matched_confounder_family": confounder,
                "pair_group_column": group_column,
                "target_rows": int(len(target)),
                "target_pair_group_count": int(len(target_groups)),
                "matched_confounder_rows": int(len(matched)),
                "matched_confounder_pair_group_count": int(len(matched_groups)),
                "paired_group_count": int(len(paired_groups)),
                "target_pair_coverage": float(coverage),
                "physically_matched_group_count": int(physically_matched_groups),
                "target_physical_pair_coverage": float(physical_coverage),
                "missing_target_pair_group_count": int(len(target_groups - matched_groups)),
                "physical_mismatch_group_count": int(len(mismatched_physical_groups)),
                "is_usenix_ready": bool(coverage >= args.min_coverage and physical_coverage >= args.min_coverage),
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(output)
    if args.fail_under_min:
        failures = [
            row
            for row in rows
            if float(row["target_pair_coverage"]) < args.min_coverage
            or float(row["target_physical_pair_coverage"]) < args.min_coverage
        ]
        if failures:
            families = ", ".join(str(row["attack_family"]) for row in failures)
            raise SystemExit(
                f"Counterfactual triad or physical coverage below {args.min_coverage:.2f} for: {families}"
            )


if __name__ == "__main__":
    main()
