from __future__ import annotations

import sys
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import load_yaml_config, resolve_path, write_json
from src.data.load_metadata import load_dataset_config, load_or_build_canonical_metadata, resolve_pdf_path
from src.features.schema import (
    ANALYSIS_ONLY_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    FEATURE_SCHEMA_VERSION,
    FORBIDDEN_FEATURE_COLUMNS,
    GENERATION_PROCESS_COLUMNS,
    REQUIRED_METADATA_COLUMNS,
)
from src.parsers.extractor_checks import dependency_report
from src.parsers.pdf_features import extract_pdf_features


def load_features_config(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    payload = load_yaml_config(config)
    if not isinstance(payload, dict):
        raise ValueError("Feature config must be a mapping.")
    return payload


def build_features(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    feature_config = load_features_config(config)
    configured_schema_version = feature_config.get("feature_schema_version", FEATURE_SCHEMA_VERSION)
    if configured_schema_version != FEATURE_SCHEMA_VERSION:
        raise ValueError(
            "Feature config schema version mismatch: "
            f"{configured_schema_version!r} != code schema {FEATURE_SCHEMA_VERSION!r}"
        )
    dataset_config = load_dataset_config(feature_config["dataset_config"])
    metadata = load_or_build_canonical_metadata(dataset_config)

    feature_rows: list[dict[str, Any]] = []
    resolved_paths: list[str] = []
    parse_errors: list[int] = []
    total = len(metadata)
    extractor_config = feature_config.get("extractor", {})
    workers = max(
        1,
        int(os.environ.get("SOLVANCE_FEATURE_WORKERS") or feature_config.get("extraction_workers", 1) or 1),
    )
    progress_every = max(1, int(feature_config.get("progress_every", 250) or 250))

    rows = list(metadata.itertuples(index=False))
    if workers == 1:
        iterator = (_extract_one_feature_row(row, dataset_config, extractor_config) for row in rows)
        for index, result in enumerate(iterator, start=1):
            _append_feature_result(result, feature_rows, resolved_paths, parse_errors)
            _log_progress(index, total, progress_every)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_extract_one_feature_row, row, dataset_config, extractor_config)
                for row in rows
            ]
            for index, future in enumerate(futures, start=1):
                _append_feature_result(future.result(), feature_rows, resolved_paths, parse_errors)
                _log_progress(index, total, progress_every)

    features_df = pd.DataFrame.from_records(feature_rows).sort_values("pdf_id").reset_index(drop=True)
    ordered_columns = ["pdf_id", *FEATURE_COLUMNS]
    features_df = features_df.loc[:, ordered_columns]

    labels_df = metadata.sort_values("pdf_id").reset_index(drop=True).copy()
    labels_df["resolved_file_path"] = resolved_paths
    labels_df["parse_errors"] = parse_errors
    labels_df["feature_schema_version"] = configured_schema_version

    features_path = resolve_path(feature_config["output_features_path"])
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_parquet(features_path, index=False)

    labels_path = resolve_path(feature_config["output_labels_path"])
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_df.to_parquet(labels_path, index=False)

    canonical_output_path = resolve_path(feature_config["output_canonical_metadata_path"])
    canonical_output_path.parent.mkdir(parents=True, exist_ok=True)
    labels_df.to_parquet(canonical_output_path, index=False)

    schema_output_path = resolve_path(
        feature_config.get("feature_schema_output_path", "data/artifacts/feature_schema.json")
    )
    write_json(
        {
            "feature_schema_version": feature_config.get(
                "feature_schema_version", configured_schema_version
            ),
            "feature_columns": FEATURE_COLUMNS,
            "feature_groups": FEATURE_GROUPS,
            "required_metadata_columns": REQUIRED_METADATA_COLUMNS,
            "analysis_only_columns": ANALYSIS_ONLY_COLUMNS,
            "forbidden_feature_columns": sorted(FORBIDDEN_FEATURE_COLUMNS),
            "generation_process_columns": GENERATION_PROCESS_COLUMNS,
        },
        schema_output_path,
    )

    report = dependency_report()
    return {
        "num_documents": int(len(features_df)),
        "features_path": str(features_path),
        "labels_path": str(labels_path),
        "canonical_metadata_path": str(canonical_output_path),
        "feature_schema_path": str(schema_output_path),
        "dependency_report": report,
    }


def _extract_one_feature_row(row: Any, dataset_config: dict[str, Any], extractor_config: dict[str, Any]) -> dict[str, Any]:
    resolved_path = resolve_pdf_path(row.file_path, dataset_config)
    extraction = extract_pdf_features(resolved_path, extractor_config)
    return {
        "feature_row": {"pdf_id": row.pdf_id, **extraction["features"]},
        "resolved_path": str(resolved_path),
        "parse_errors": int(extraction["parse_errors"]),
    }


def _append_feature_result(
    result: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    resolved_paths: list[str],
    parse_errors: list[int],
) -> None:
    feature_rows.append(result["feature_row"])
    resolved_paths.append(result["resolved_path"])
    parse_errors.append(result["parse_errors"])


def _log_progress(index: int, total: int, progress_every: int) -> None:
    if index == 1 or index == total or index % progress_every == 0:
        print(f"[build-features] {index}/{total}", file=sys.stderr, flush=True)
