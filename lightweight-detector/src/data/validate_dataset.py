from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.common import write_json
from src.data.load_metadata import load_dataset_config, load_or_build_canonical_metadata, resolve_pdf_path
from src.features.schema import BENIGN_REGIME_VALUE, REGIME_COLUMNS, REQUIRED_METADATA_COLUMNS


def validate_dataset(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    dataset_config = load_dataset_config(config)
    frame = load_or_build_canonical_metadata(dataset_config)
    benign_value = dataset_config.get("benign_regime_value", BENIGN_REGIME_VALUE)

    errors: list[str] = []
    warnings: list[str] = []

    missing_columns = [column for column in REQUIRED_METADATA_COLUMNS if column not in frame.columns]
    if missing_columns:
        errors.append(f"Missing required metadata columns: {', '.join(sorted(missing_columns))}")

    duplicate_ids = frame[frame["pdf_id"].duplicated()]["pdf_id"].tolist()
    if duplicate_ids:
        errors.append(f"Duplicate pdf_id values: {duplicate_ids[:10]}")

    invalid_labels = sorted(set(frame.loc[~frame["label"].isin(dataset_config["allowed_labels"]), "label"].tolist()))
    if invalid_labels:
        errors.append(f"Invalid labels outside allowed set: {invalid_labels}")

    class_counts = frame["label"].value_counts().sort_index().to_dict()
    if len(class_counts) >= 2:
        counts = sorted(class_counts.values())
        if counts[0] / max(counts[-1], 1) < 0.5:
            warnings.append(
                f"Label imbalance detected: class counts {class_counts}. Pairing may not be balanced enough."
            )

    enum_checks = {
        "source_type": dataset_config.get("allowed_source_types", []),
        "spatial_regime": dataset_config.get("allowed_spatial_regimes", []),
        "rendering_regime": dataset_config.get("allowed_rendering_regimes", []),
        "structural_regime": dataset_config.get("allowed_structural_regimes", []),
        "message_type": dataset_config.get("allowed_message_types", []),
        "attack_family": dataset_config.get("allowed_attack_families", []),
        "attack_strength": dataset_config.get("allowed_attack_strengths", []),
        "benign_confounder_family": dataset_config.get("allowed_benign_confounder_families", []),
    }
    for column, allowed_values in enum_checks.items():
        if not allowed_values:
            continue
        invalid_values = sorted(set(frame.loc[~frame[column].isin(allowed_values), column].tolist()))
        if invalid_values:
            errors.append(f"Invalid values for {column}: {invalid_values}")

    benign_rows = frame["label"] == 0
    for column in [
        "spatial_regime",
        "rendering_regime",
        "structural_regime",
        "message_type",
        "attack_family",
        "attack_strength",
    ]:
        inconsistent = frame.loc[benign_rows & (frame[column] != benign_value), ["pdf_id", column]]
        if not inconsistent.empty:
            errors.append(
                f"Benign rows must use '{benign_value}' for {column}; found {len(inconsistent)} violations."
            )

    file_records: list[dict[str, Any]] = []
    missing_files: list[str] = []
    for row in frame.itertuples(index=False):
        resolved = resolve_pdf_path(row.file_path, dataset_config)
        exists = resolved.exists()
        if not exists:
            missing_files.append(str(resolved))
        file_records.append({"pdf_id": row.pdf_id, "resolved_path": str(resolved), "exists": exists})
    if missing_files:
        errors.append(f"Missing PDF files: {missing_files[:10]}")

    group_column = dataset_config.get("group_column", "base_pdf_id")
    if group_column not in frame.columns:
        errors.append(f"Grouping column '{group_column}' is missing.")
    else:
        group_summary = (
            frame.groupby(group_column)
            .agg(num_rows=("pdf_id", "count"), labels=("label", lambda values: sorted(set(values))))
            .reset_index()
        )
        invalid_groups = group_summary[group_summary["labels"].map(lambda values: values != [0, 1] and values != [0, 1, 1])]
        # Allow multiple injected rows by checking membership rather than exact multiplicity.
        invalid_groups = group_summary[
            group_summary["labels"].map(lambda values: not ({0, 1}.issubset(set(values))))
        ]
        if not invalid_groups.empty:
            errors.append(
                f"Found {len(invalid_groups)} groups without both benign and injected members."
            )

        physical_pairs = [
            ("target_physical_attack_family", "confounder_physical_attack_family"),
            ("target_physical_attack_strength", "confounder_physical_attack_strength"),
            ("target_physical_spatial_regime", "confounder_physical_spatial_regime"),
            ("target_physical_rendering_regime", "confounder_physical_rendering_regime"),
            ("target_physical_structural_regime", "confounder_physical_structural_regime"),
            ("target_physical_artifact_wrapper", "confounder_physical_artifact_wrapper"),
        ]
        if all(column in frame.columns for pair in physical_pairs for column in pair):
            confounders = frame[
                (frame["pdf_role"].astype(str) == "benign_confounder")
                & (frame["benign_confounder_family"].astype(str) != "none")
            ]
            mismatched = []
            for row in confounders.itertuples(index=False):
                for target_column, confounder_column in physical_pairs:
                    if str(getattr(row, target_column)) != str(getattr(row, confounder_column)):
                        mismatched.append(str(getattr(row, "pdf_id")))
                        break
            if mismatched:
                errors.append(
                    "Benign confounder physical regimes must match injected targets; "
                    f"found {len(mismatched)} mismatches, examples: {mismatched[:10]}"
                )

    source_label_table = pd.crosstab(frame["source_type"], frame["label"])
    exclusive_source_types = [
        str(source_type)
        for source_type, row in source_label_table.iterrows()
        if int((row > 0).sum()) == 1
    ]
    if exclusive_source_types:
        warnings.append(
            "Some source types appear in only one class label, which risks source leakage: "
            + ", ".join(sorted(exclusive_source_types))
        )

    for column in REGIME_COLUMNS:
        if column not in frame.columns:
            continue
        low_count_values = (
            frame[column]
            .value_counts(dropna=False)
            .loc[lambda values: values < 3]
            .index
            .tolist()
        )
        if low_count_values:
            warnings.append(
                f"{column} has sparse values with fewer than 3 samples: {low_count_values[:10]}"
            )

    split_path = Path(str(dataset_config.get("split_output_path", "")))
    split_issues: list[str] = []
    split_warnings: list[str] = []
    if str(split_path) and split_path.exists():
        split_issues = _validate_existing_splits(frame, dataset_config)
        errors.extend(split_issues)
        split_warnings = _split_coverage_warnings(frame, dataset_config)
        warnings.extend(split_warnings)

    report = {
        "overall_passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "num_rows": int(len(frame)),
        "num_groups": int(frame[group_column].nunique()) if group_column in frame.columns else 0,
        "class_counts": class_counts,
        "per_regime_counts": {
            column: frame[column].value_counts(dropna=False).to_dict()
            for column in REGIME_COLUMNS
            if column in frame.columns
        },
        "source_label_counts": source_label_table.to_dict(),
        "missing_field_report": {
            column: int(frame[column].isna().sum() + (frame[column].astype(str).str.len() == 0).sum())
            for column in REQUIRED_METADATA_COLUMNS
            if column in frame.columns
        },
        "file_checks": file_records[:20],
        "existing_split_issues": split_issues,
        "split_coverage_warnings": split_warnings,
    }
    write_json(report, dataset_config["validation_report_path"])
    return report


def _validate_existing_splits(frame: pd.DataFrame, dataset_config: dict[str, Any]) -> list[str]:
    import json

    issues: list[str] = []
    split_path = Path(dataset_config["split_output_path"])
    with split_path.open("r", encoding="utf-8") as handle:
        split_payload = json.load(handle)

    memberships: dict[str, str] = {}
    for split_name in ["train_ids", "val_ids", "test_ids"]:
        for pdf_id in split_payload.get(split_name, []):
            memberships[pdf_id] = split_name

    subset = frame[frame["pdf_id"].isin(memberships)]
    if subset.empty:
        issues.append("Saved split file exists but contains no known pdf_ids.")
        return issues

    group_column = dataset_config.get("group_column", "base_pdf_id")
    grouped = subset.groupby(group_column)["pdf_id"].apply(list)
    for group_value, pdf_ids in grouped.items():
        split_names = {memberships[pdf_id] for pdf_id in pdf_ids}
        if len(split_names) > 1:
            issues.append(f"Group '{group_value}' is split across {sorted(split_names)}.")
    return issues


def _split_coverage_warnings(frame: pd.DataFrame, dataset_config: dict[str, Any]) -> list[str]:
    import json

    warnings: list[str] = []
    split_path = Path(dataset_config["split_output_path"])
    with split_path.open("r", encoding="utf-8") as handle:
        split_payload = json.load(handle)

    memberships: dict[str, str] = {}
    for split_name in ["train_ids", "val_ids", "test_ids"]:
        normalized = split_name.replace("_ids", "")
        for pdf_id in split_payload.get(split_name, []):
            memberships[pdf_id] = normalized

    subset = frame[frame["pdf_id"].isin(memberships)].copy()
    if subset.empty:
        return warnings
    subset["split_name"] = subset["pdf_id"].map(memberships)

    coverage_columns = list(dict.fromkeys(["source_type", *REGIME_COLUMNS]))
    split_cfg = dataset_config.get("split", {}) or {}
    heldout_column = str(split_cfg.get("heldout_column", "")).strip()
    heldout_values = {str(value) for value in split_cfg.get("heldout_values", []) or []}
    for column in coverage_columns:
        if column not in subset.columns:
            continue
        coverage = pd.crosstab(subset[column], subset["split_name"])
        for value, row in coverage.iterrows():
            is_expected_holdout = column == heldout_column and str(value) in heldout_values
            if "train" in coverage.columns and int(row.get("train", 0)) == 0 and not is_expected_holdout:
                warnings.append(f"{column}='{value}' is absent from train split.")
            if "test" in coverage.columns and int(row.get("test", 0)) == 0:
                warnings.append(f"{column}='{value}' is absent from test split.")
    return warnings
