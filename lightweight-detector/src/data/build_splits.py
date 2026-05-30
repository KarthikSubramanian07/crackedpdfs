from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import read_json, write_json
from src.data.load_metadata import load_dataset_config, load_or_build_canonical_metadata


def build_grouped_splits(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    dataset_config = load_dataset_config(config)
    frame = load_or_build_canonical_metadata(dataset_config)
    group_column = dataset_config.get("group_column", "base_pdf_id")
    if group_column not in frame.columns:
        raise ValueError(f"Grouping column '{group_column}' not present in canonical metadata.")

    unique_groups = sorted(frame[group_column].dropna().astype(str).unique().tolist())
    if len(unique_groups) < 3:
        raise ValueError("Need at least three unique groups to build train/val/test splits.")

    split_cfg = dataset_config.get("split", {})
    train_size = float(split_cfg.get("train_size", 0.8))
    val_size = float(split_cfg.get("val_size", 0.1))
    test_size = float(split_cfg.get("test_size", 0.1))
    total = train_size + val_size + test_size
    if abs(total - 1.0) > 1e-6:
        raise ValueError("train_size + val_size + test_size must sum to 1.0")

    strategy = str(split_cfg.get("strategy", "random_grouped")).strip().lower()
    holdout_summary: dict[str, Any] | None = None
    if strategy == "coverage_aware":
        memberships = _build_coverage_aware_memberships(
            frame,
            group_column=group_column,
            split_cfg=split_cfg,
            random_state=int(dataset_config.get("random_state", 42)),
        )
    elif strategy in {
        "heldout_message_type",
        "heldout_attack_family",
        "heldout_source_filename",
        "heldout_source_type",
        "heldout_source_stratum",
        "heldout_provenance",
    }:
        default_column = {
            "heldout_message_type": "message_type",
            "heldout_attack_family": "attack_family",
            "heldout_source_filename": "source_original_filename",
            "heldout_source_type": "source_type",
            "heldout_source_stratum": "benign_stratum_key",
            "heldout_provenance": "source_original_filename",
        }[strategy]
        memberships, holdout_summary = _build_heldout_memberships(
            frame,
            group_column=group_column,
            split_cfg=split_cfg,
            random_state=int(dataset_config.get("random_state", 42)),
            default_column=default_column,
        )
    else:
        memberships = _build_random_memberships(
            unique_groups,
            train_size=train_size,
            val_size=val_size,
            random_state=int(dataset_config.get("random_state", 42)),
        )

    frame = frame.copy()
    frame["split_assignment"] = frame[group_column].map(memberships)
    train_groups = sorted(group_value for group_value, split_name in memberships.items() if split_name == "train")
    val_groups = sorted(group_value for group_value, split_name in memberships.items() if split_name == "val")
    test_groups = sorted(group_value for group_value, split_name in memberships.items() if split_name == "test")

    payload = {
        "train_ids": sorted(frame.loc[frame["split_assignment"] == "train", "pdf_id"].tolist()),
        "val_ids": sorted(frame.loc[frame["split_assignment"] == "val", "pdf_id"].tolist()),
        "test_ids": sorted(frame.loc[frame["split_assignment"] == "test", "pdf_id"].tolist()),
        "train_groups": train_groups,
        "val_groups": val_groups,
        "test_groups": test_groups,
        "group_column": group_column,
        "random_state": int(dataset_config.get("random_state", 42)),
        "split_strategy": strategy,
    }
    if holdout_summary is not None:
        payload["holdout"] = holdout_summary
    write_json(payload, dataset_config["split_output_path"])
    return payload


def load_splits(path_like: str | Path) -> dict[str, Any]:
    return read_json(path_like)


def subset_for_split(frame: pd.DataFrame, splits: dict[str, Any], split_name: str) -> pd.DataFrame:
    key = f"{split_name}_ids"
    ids = splits.get(key, [])
    return frame[frame["pdf_id"].isin(ids)].copy()


def _build_random_memberships(
    unique_groups: list[str],
    *,
    train_size: float,
    val_size: float,
    random_state: int,
) -> dict[str, str]:
    rng = random.Random(random_state)
    shuffled_groups = unique_groups[:]
    rng.shuffle(shuffled_groups)

    n_groups = len(shuffled_groups)
    n_train = max(1, int(round(n_groups * train_size)))
    n_val = max(1, int(round(n_groups * val_size)))
    n_test = n_groups - n_train - n_val
    if n_test < 1:
        n_test = 1
        if n_train > n_val:
            n_train -= 1
        else:
            n_val -= 1

    train_groups = set(shuffled_groups[:n_train])
    val_groups = set(shuffled_groups[n_train:n_train + n_val])
    test_groups = set(shuffled_groups[n_train + n_val:])
    if not test_groups:
        moved = val_groups.pop()
        test_groups.add(moved)

    memberships: dict[str, str] = {}
    for group_value in train_groups:
        memberships[group_value] = "train"
    for group_value in val_groups:
        memberships[group_value] = "val"
    for group_value in test_groups:
        memberships[group_value] = "test"
    return memberships


def _build_coverage_aware_memberships(
    frame: pd.DataFrame,
    *,
    group_column: str,
    split_cfg: dict[str, Any],
    random_state: int,
) -> dict[str, str]:
    split_names = ["train", "val", "test"]
    train_size = float(split_cfg.get("train_size", 0.8))
    val_size = float(split_cfg.get("val_size", 0.1))
    test_size = float(split_cfg.get("test_size", 0.1))
    target_doc_counts = {
        "train": float(len(frame) * train_size),
        "val": float(len(frame) * val_size),
        "test": float(len(frame) * test_size),
    }
    group_counts = frame[group_column].value_counts()
    train_group_target = max(1, int(round(len(group_counts) * train_size)))
    val_group_target = max(1, int(round(len(group_counts) * val_size)))
    target_group_counts = {
        "train": train_group_target,
        "val": val_group_target,
        "test": max(1, len(group_counts) - train_group_target - val_group_target),
    }
    if target_group_counts["test"] < 1:
        target_group_counts["test"] = 1

    coverage_columns = [
        str(column)
        for column in split_cfg.get("coverage_columns", []) or []
        if str(column) in frame.columns
    ]
    excluded_values = {
        str(column): {str(value) for value in values}
        for column, values in (split_cfg.get("coverage_exclude_values", {}) or {}).items()
    }

    group_features = _build_group_feature_map(
        frame,
        group_column=group_column,
        coverage_columns=coverage_columns,
        excluded_values=excluded_values,
    )
    coverage_counts = _coverage_frequency(group_features)

    rng = random.Random(random_state)
    ordered_groups = list(group_features.keys())
    rng.shuffle(ordered_groups)
    ordered_groups.sort(
        key=lambda group_value: (
            -_group_rarity_score(group_features[group_value]["coverage"], coverage_counts),
            -int(group_features[group_value]["doc_count"]),
        )
    )

    assigned_docs = {split_name: 0 for split_name in split_names}
    assigned_groups = {split_name: 0 for split_name in split_names}
    covered_values = {split_name: set() for split_name in split_names}
    memberships: dict[str, str] = {}

    for group_value in ordered_groups:
        doc_count = int(group_features[group_value]["doc_count"])
        coverage = group_features[group_value]["coverage"]
        split_name = _best_split_for_group(
            doc_count=doc_count,
            coverage=coverage,
            split_names=split_names,
            target_doc_counts=target_doc_counts,
            target_group_counts=target_group_counts,
            assigned_docs=assigned_docs,
            assigned_groups=assigned_groups,
            covered_values=covered_values,
            coverage_counts=coverage_counts,
        )
        memberships[group_value] = split_name
        assigned_docs[split_name] += doc_count
        assigned_groups[split_name] += 1
        covered_values[split_name].update(coverage)

    _repair_missing_coverage(
        memberships,
        group_features=group_features,
        split_names=["val", "test"],
        assigned_groups=assigned_groups,
        covered_values=covered_values,
        target_doc_counts=target_doc_counts,
        assigned_docs=assigned_docs,
    )
    return memberships


def _build_heldout_memberships(
    frame: pd.DataFrame,
    *,
    group_column: str,
    split_cfg: dict[str, Any],
    random_state: int,
    default_column: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    holdout_column = str(split_cfg.get("heldout_column", default_column)).strip() or default_column
    if holdout_column not in frame.columns:
        raise ValueError(f"Held-out split requires column '{holdout_column}' in canonical metadata.")

    holdout_values = [str(value) for value in split_cfg.get("heldout_values", []) or [] if str(value).strip()]
    if not holdout_values:
        if holdout_column in {
            "source_original_filename",
            "source_type",
            "benign_stratum_key",
            "layout_complexity",
            "font_band",
            "freeze_version",
        }:
            holdout_values = _default_provenance_holdout_values(
                frame,
                holdout_column,
                group_column=group_column,
                test_size=float(split_cfg.get("test_size", 0.1)),
                random_state=random_state,
            )
        else:
            holdout_values = _default_holdout_values(frame, holdout_column)
    holdout_set = set(holdout_values)
    if not holdout_set:
        raise ValueError(f"No held-out values available for column '{holdout_column}'.")

    group_tokens = (
        frame.groupby(group_column)[holdout_column]
        .apply(lambda series: {str(value) for value in series.dropna().astype(str).tolist()})
        .to_dict()
    )
    test_groups = sorted(
        str(group_value)
        for group_value, values in group_tokens.items()
        if any(value in holdout_set for value in values)
    )
    if not test_groups:
        raise ValueError(
            f"Held-out split for column '{holdout_column}' found no groups containing values {sorted(holdout_set)}."
        )

    remaining_groups = sorted(
        str(group_value) for group_value in frame[group_column].dropna().astype(str).unique().tolist() if str(group_value) not in set(test_groups)
    )
    if len(remaining_groups) < 2:
        raise ValueError("Held-out split leaves fewer than two groups for train/val.")

    train_size = float(split_cfg.get("train_size", 0.8))
    val_size = float(split_cfg.get("val_size", 0.1))
    memberships = _build_train_val_memberships(
        remaining_groups,
        train_size=train_size / max(train_size + val_size, 1e-9),
        random_state=random_state,
    )
    for group_value in test_groups:
        memberships[group_value] = "test"

    summary = {
        "column": holdout_column,
        "values": sorted(holdout_set),
        "test_groups": test_groups,
    }
    return memberships, summary


def _default_holdout_values(frame: pd.DataFrame, column: str) -> list[str]:
    non_benign = frame.loc[
        (frame["label"].astype(int) == 1) & frame[column].notna(),
        column,
    ].astype(str)
    values = sorted(value for value in non_benign.unique().tolist() if value and value != "none")
    if not values:
        return []
    return [values[-1]]


def _default_provenance_holdout_values(
    frame: pd.DataFrame,
    column: str,
    *,
    group_column: str,
    test_size: float,
    random_state: int,
) -> list[str]:
    if column not in frame.columns:
        return []
    group_values = (
        frame[[group_column, column]]
        .dropna()
        .astype(str)
        .drop_duplicates()
    )
    value_to_groups: dict[str, set[str]] = {}
    for row in group_values.itertuples(index=False):
        group_value = str(getattr(row, group_column))
        holdout_value = str(getattr(row, column))
        if not holdout_value or holdout_value == "none":
            continue
        value_to_groups.setdefault(holdout_value, set()).add(group_value)

    if not value_to_groups:
        return []

    rng = random.Random(random_state)
    values = list(value_to_groups.keys())
    rng.shuffle(values)
    values.sort(key=lambda value: (-len(value_to_groups[value]), value))

    target_groups = max(1, int(round(frame[group_column].astype(str).nunique() * test_size)))
    selected: list[str] = []
    selected_groups: set[str] = set()
    for value in values:
        selected.append(value)
        selected_groups.update(value_to_groups[value])
        if len(selected_groups) >= target_groups:
            break
    return selected


def _build_train_val_memberships(
    unique_groups: list[str],
    *,
    train_size: float,
    random_state: int,
) -> dict[str, str]:
    rng = random.Random(random_state)
    shuffled_groups = unique_groups[:]
    rng.shuffle(shuffled_groups)

    n_groups = len(shuffled_groups)
    n_train = max(1, int(round(n_groups * train_size)))
    if n_train >= n_groups:
        n_train = n_groups - 1

    train_groups = set(shuffled_groups[:n_train])
    val_groups = set(shuffled_groups[n_train:])
    if not val_groups:
        moved = train_groups.pop()
        val_groups.add(moved)

    memberships: dict[str, str] = {}
    for group_value in train_groups:
        memberships[group_value] = "train"
    for group_value in val_groups:
        memberships[group_value] = "val"
    return memberships


def _build_group_feature_map(
    frame: pd.DataFrame,
    *,
    group_column: str,
    coverage_columns: list[str],
    excluded_values: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for group_value, group in frame.groupby(group_column):
        coverage: set[tuple[str, str]] = set()
        for column in coverage_columns:
            blocked = excluded_values.get(column, set())
            for value in group[column].dropna().astype(str).unique().tolist():
                if value in blocked:
                    continue
                coverage.add((column, value))
        features[str(group_value)] = {
            "doc_count": int(len(group)),
            "coverage": coverage,
        }
    return features


def _coverage_frequency(group_features: dict[str, dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for payload in group_features.values():
        for token in payload["coverage"]:
            counts[token] = counts.get(token, 0) + 1
    return counts


def _group_rarity_score(coverage: set[tuple[str, str]], coverage_counts: dict[tuple[str, str], int]) -> float:
    score = 0.0
    for token in coverage:
        count = max(coverage_counts.get(token, 1), 1)
        score += 1.0 / float(count)
    return score


def _best_split_for_group(
    *,
    doc_count: int,
    coverage: set[tuple[str, str]],
    split_names: list[str],
    target_doc_counts: dict[str, float],
    target_group_counts: dict[str, int],
    assigned_docs: dict[str, int],
    assigned_groups: dict[str, int],
    covered_values: dict[str, set[tuple[str, str]]],
    coverage_counts: dict[tuple[str, str], int],
) -> str:
    best_split = split_names[0]
    best_score = float("-inf")
    for split_name in split_names:
        uncovered_gain = sum(
            1.0 / float(max(coverage_counts.get(token, 1), 1))
            for token in coverage
            if token not in covered_values[split_name]
        )
        remaining_doc_ratio = (
            (target_doc_counts[split_name] - assigned_docs[split_name]) / max(target_doc_counts[split_name], 1.0)
        )
        doc_penalty = max(
            0.0,
            (assigned_docs[split_name] + doc_count - target_doc_counts[split_name]) / max(target_doc_counts[split_name], 1.0),
        )
        group_penalty = max(
            0.0,
            (assigned_groups[split_name] + 1 - target_group_counts[split_name]) / max(target_group_counts[split_name], 1),
        )
        score = (100.0 * uncovered_gain) + (10.0 * remaining_doc_ratio) - (25.0 * doc_penalty) - (10.0 * group_penalty)
        if score > best_score:
            best_score = score
            best_split = split_name
    return best_split


def _repair_missing_coverage(
    memberships: dict[str, str],
    *,
    group_features: dict[str, dict[str, Any]],
    split_names: list[str],
    assigned_groups: dict[str, int],
    covered_values: dict[str, set[tuple[str, str]]],
    target_doc_counts: dict[str, float],
    assigned_docs: dict[str, int],
) -> None:
    all_tokens = set()
    for payload in group_features.values():
        all_tokens.update(payload["coverage"])

    for split_name in split_names:
        missing = [token for token in all_tokens if token not in covered_values[split_name]]
        for token in missing:
            candidate_group = _find_best_repair_group(
                memberships,
                token=token,
                target_split=split_name,
                group_features=group_features,
                assigned_groups=assigned_groups,
                target_doc_counts=target_doc_counts,
                assigned_docs=assigned_docs,
            )
            if candidate_group is None:
                continue
            source_split = memberships[candidate_group]
            if source_split == split_name:
                continue
            memberships[candidate_group] = split_name
            assigned_groups[source_split] -= 1
            assigned_groups[split_name] += 1
            doc_count = int(group_features[candidate_group]["doc_count"])
            assigned_docs[source_split] -= doc_count
            assigned_docs[split_name] += doc_count
            covered_values[split_name].update(group_features[candidate_group]["coverage"])


def _find_best_repair_group(
    memberships: dict[str, str],
    *,
    token: tuple[str, str],
    target_split: str,
    group_features: dict[str, dict[str, Any]],
    assigned_groups: dict[str, int],
    target_doc_counts: dict[str, float],
    assigned_docs: dict[str, int],
) -> str | None:
    best_group: str | None = None
    best_cost = float("inf")
    for group_value, payload in group_features.items():
        if token not in payload["coverage"]:
            continue
        source_split = memberships[group_value]
        if source_split == target_split or assigned_groups[source_split] <= 1:
            continue
        doc_count = int(payload["doc_count"])
        source_cost = abs((assigned_docs[source_split] - doc_count) - target_doc_counts[source_split])
        target_cost = abs((assigned_docs[target_split] + doc_count) - target_doc_counts[target_split])
        cost = source_cost + target_cost
        if cost < best_cost:
            best_cost = cost
            best_group = group_value
    return best_group


def _invert_memberships(memberships: dict[str, str]) -> dict[str, list[str]]:
    output = {"train": [], "val": [], "test": []}
    for group_value, split_name in memberships.items():
        output.setdefault(split_name, []).append(group_value)
    return output
