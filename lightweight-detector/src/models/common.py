from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import load_yaml_config, resolve_path, utc_timestamp_tag, write_json
from src.data.build_splits import load_splits


def load_training_config(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    return load_yaml_config(config)


def load_training_tables(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    features = pd.read_parquet(resolve_path(config["features_path"]))
    labels = pd.read_parquet(resolve_path(config["labels_path"]))
    splits = load_splits(resolve_path(config["splits_path"]))
    return features, labels, splits


def merge_features_and_labels(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    merged = labels.merge(features, on="pdf_id", how="inner", validate="one_to_one")
    if merged.empty:
        raise ValueError("Merged training frame is empty.")
    return merged


def split_merged_frame(merged: pd.DataFrame, splits: dict[str, Any]) -> dict[str, pd.DataFrame]:
    output = {}
    for split_name in ["train", "val", "test"]:
        ids = splits.get(f"{split_name}_ids", [])
        frame = merged[merged["pdf_id"].isin(ids)].copy().reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"Split '{split_name}' is empty.")
        output[split_name] = frame
    return output


def load_extractor_config(training_config: dict[str, Any]) -> dict[str, Any]:
    features_config_path = training_config.get("features_config")
    if not features_config_path:
        return {}
    payload = load_yaml_config(features_config_path)
    return payload.get("extractor", {}) or {}


def persist_artifact(
    artifact: dict[str, Any],
    *,
    output_model_path: str | Path,
    output_metrics_path: str | Path,
    metrics_payload: dict[str, Any],
) -> dict[str, str]:
    model_path = resolve_path(output_model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    artifact["created_at"] = utc_timestamp_tag()
    with model_path.open("wb") as handle:
        pickle.dump(artifact, handle)

    metrics_path = resolve_path(output_metrics_path)
    metrics_payload = dict(metrics_payload)
    metrics_payload["model_path"] = str(model_path)
    write_json(metrics_payload, metrics_path)
    return {
        "model_path": str(model_path),
        "metrics_path": str(metrics_path),
    }
