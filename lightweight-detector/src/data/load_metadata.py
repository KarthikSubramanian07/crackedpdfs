from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.common import coerce_bool, coerce_int, load_yaml_config, resolve_path, write_jsonl
from src.features.schema import BENIGN_REGIME_VALUE, REQUIRED_METADATA_COLUMNS


def load_dataset_config(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, dict):
        payload = config
        if "dataset" not in payload:
            return payload
    else:
        payload = load_yaml_config(config)
    if "dataset" not in payload:
        raise ValueError("Dataset config must contain a top-level 'dataset' mapping.")
    dataset_config = payload["dataset"] or {}
    if not isinstance(dataset_config, dict):
        raise ValueError("dataset config must be a mapping.")
    return dataset_config


def load_or_build_canonical_metadata(config: str | Path | dict[str, Any]) -> pd.DataFrame:
    dataset_config = load_dataset_config(config)
    canonical_path = resolve_path(dataset_config["canonical_metadata_path"])
    if canonical_path.exists():
        frame = _load_canonical_frame(canonical_path)
    else:
        frame = _normalize_sample_metadata(dataset_config)
    frame = _finalize_canonical_frame(frame, dataset_config)
    persist_canonical_metadata(frame, dataset_config)
    return frame


def persist_canonical_metadata(frame: pd.DataFrame, dataset_config: dict[str, Any]) -> None:
    jsonl_path = resolve_path(dataset_config["canonical_metadata_output_path"])
    parquet_path = resolve_path(dataset_config["canonical_metadata_parquet_path"])
    write_jsonl(frame.to_dict(orient="records"), jsonl_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, index=False)


def resolve_pdf_path(file_path: str, dataset_config: dict[str, Any]) -> Path:
    raw_dir = resolve_path(dataset_config["raw_dir"])
    path = Path(file_path)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append((raw_dir / path).resolve())
        candidates.append(resolve_path(path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if candidates:
        return candidates[0]
    return path


def _load_canonical_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return pd.DataFrame.from_records(records)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame.from_records(payload)
        raise ValueError(f"Canonical metadata JSON must be a list: {path}")
    raise ValueError(f"Unsupported canonical metadata format: {path}")


def _normalize_sample_metadata(dataset_config: dict[str, Any]) -> pd.DataFrame:
    sample_dir = resolve_path(dataset_config["sample_metadata_dir"])
    run_metadata_path = resolve_path(dataset_config["run_metadata_path"])
    if not sample_dir.exists():
        raise FileNotFoundError(
            f"No canonical metadata found and sample metadata directory is missing: {sample_dir}"
        )

    run_metadata: dict[str, Any] = {}
    if run_metadata_path.exists():
        run_metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))

    benign_dir = resolve_path(dataset_config["benign_pdf_dir"])
    injected_dir = resolve_path(dataset_config["injected_pdf_dir"])
    raw_dir = resolve_path(dataset_config["raw_dir"])
    benign_value = dataset_config.get("benign_regime_value", BENIGN_REGIME_VALUE)

    records: list[dict[str, Any]] = []
    for sample_path in sorted(sample_dir.glob("*.metadata.json")):
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        target_physical = _physical_regime(payload, "target_physical_regime")
        confounder_physical = _physical_regime(payload, "confounder_physical_regime")

        sample_id = payload["sample_id"]
        base_pdf_id = payload.get("base_pdf_id") or payload.get("pair_id") or sample_id
        pair_id = payload.get("pair_id")
        triad_id = payload.get("triad_id") or pair_id or sample_id
        source_document_id = payload.get("source_document_id")
        benign_registry = payload.get("benign_registry") or {}
        source_type = benign_registry.get("source_type") or "unknown"
        layout_complexity = benign_registry.get("layout_complexity")
        font_band = benign_registry.get("font_band")
        seed = payload.get("seed", run_metadata.get("seed"))
        freeze_version = (
            payload.get("freeze_version")
            or run_metadata.get("run_id")
            or run_metadata.get("created_at")
            or "unversioned"
        )
        dataset_split = payload.get("dataset_split")

        benign_filename = (payload.get("benign_file") or {}).get("filename") or f"{sample_id}.benign.pdf"
        benign_confounder_filename = (payload.get("benign_confounder_file") or {}).get("filename")
        injected_filename = (payload.get("injected_file") or {}).get("filename") or f"{sample_id}.injected.pdf"

        benign_path = _best_relative_path(benign_dir / benign_filename, raw_dir)
        benign_confounder_path = (
            _best_relative_path(benign_dir / benign_confounder_filename, raw_dir)
            if benign_confounder_filename
            else None
        )
        injected_path = _best_relative_path(injected_dir / injected_filename, raw_dir)

        shared = {
            "base_pdf_id": base_pdf_id,
            "source_type": source_type,
            "seed": coerce_int(seed),
            "freeze_version": freeze_version,
            "split_group": base_pdf_id,
            "dataset_split": dataset_split,
            "sample_id": sample_id,
            "pair_id": pair_id,
            "triad_id": triad_id,
            "source_document_id": source_document_id,
            "source_original_filename": payload.get("source_original_filename"),
            "layout_complexity": layout_complexity,
            "font_band": font_band,
            "benign_stratum_key": payload.get("benign_stratum_key"),
            "policy_message_source": payload.get("policy_message_source"),
            "message_variant_id": payload.get("message_variant_id"),
            "target_message_type": payload.get("message_type"),
            "target_attack_family": payload.get("attack_family"),
            "target_benign_confounder_family": payload.get("benign_confounder_family") or "none",
            "target_physical_attack_family": _physical_value(
                payload, target_physical, "target_physical_attack_family", "attack_family", "none"
            ),
            "target_physical_attack_strength": _physical_value(
                payload, target_physical, "target_physical_attack_strength", "attack_strength", "none"
            ),
            "target_physical_structural_regime": _physical_value(
                payload, target_physical, "target_physical_structural_regime", "structural_regime", "none"
            ),
            "target_physical_spatial_regime": _physical_value(
                payload, target_physical, "target_physical_spatial_regime", "spatial_regime", "none"
            ),
            "target_physical_rendering_regime": _physical_value(
                payload, target_physical, "target_physical_rendering_regime", "rendering_regime", "none"
            ),
            "target_physical_artifact_wrapper": coerce_bool(
                _physical_value(
                    payload, target_physical, "target_physical_artifact_wrapper", "artifact_wrapper", False
                )
            ),
            "confounder_physical_attack_family": _physical_value(
                payload, confounder_physical, "confounder_physical_attack_family", "attack_family", "none"
            ),
            "confounder_physical_attack_strength": _physical_value(
                payload, confounder_physical, "confounder_physical_attack_strength", "attack_strength", "none"
            ),
            "confounder_physical_structural_regime": _physical_value(
                payload, confounder_physical, "confounder_physical_structural_regime", "structural_regime", "none"
            ),
            "confounder_physical_spatial_regime": _physical_value(
                payload, confounder_physical, "confounder_physical_spatial_regime", "spatial_regime", "none"
            ),
            "confounder_physical_rendering_regime": _physical_value(
                payload, confounder_physical, "confounder_physical_rendering_regime", "rendering_regime", "none"
            ),
            "confounder_physical_artifact_wrapper": coerce_bool(
                _physical_value(
                    payload, confounder_physical, "confounder_physical_artifact_wrapper", "artifact_wrapper", False
                )
            ),
            "attack_strength": payload.get("attack_strength"),
            "num_chunks": coerce_int(payload.get("num_chunks")),
            "chunk_strategy": payload.get("chunk_strategy"),
            "avg_chunk_len": payload.get("avg_chunk_len"),
            "raw_injected_text": None,
            "message_length_chars": None,
            "benign_confounder_family": payload.get("benign_confounder_family") or "none",
        }

        records.append(
            {
                **shared,
                "pdf_id": f"{sample_id}.benign",
                "pdf_role": "benign_original",
                "file_path": benign_path,
                "label": 0,
                "spatial_regime": benign_value,
                "rendering_regime": benign_value,
                "structural_regime": benign_value,
                "message_type": benign_value,
                "attack_family": benign_value,
                "artifact_wrapper": False,
                "benign_confounder_family": "none",
                "attack_strength": benign_value,
                "policy_message_source": "none",
                "message_variant_id": "none",
                "num_chunks": 0,
                "chunk_strategy": benign_value,
                "avg_chunk_len": 0.0,
            }
        )
        if benign_confounder_path:
            records.append(
                {
                    **shared,
                    "pdf_id": f"{sample_id}.benign_confounder",
                    "pdf_role": "benign_confounder",
                    "file_path": benign_confounder_path,
                    "label": 0,
                    "spatial_regime": benign_value,
                    "rendering_regime": benign_value,
                    "structural_regime": benign_value,
                    "message_type": benign_value,
                    "attack_family": benign_value,
                    "artifact_wrapper": False,
                    "attack_strength": benign_value,
                    "policy_message_source": "none",
                    "message_variant_id": "none",
                    "num_chunks": 0,
                    "chunk_strategy": benign_value,
                    "avg_chunk_len": 0.0,
                }
            )
        records.append(
            {
                **shared,
                "pdf_id": f"{sample_id}.injected",
                "pdf_role": "injected_attack",
                "file_path": injected_path,
                "label": 1,
                "spatial_regime": payload.get("spatial_regime"),
                "rendering_regime": payload.get("rendering_regime"),
                "structural_regime": payload.get("structural_regime"),
                "message_type": payload.get("message_type"),
                "attack_family": payload.get("attack_family"),
                "artifact_wrapper": coerce_bool(payload.get("artifact_wrapper")),
                "benign_confounder_family": "none",
            }
        )

    return pd.DataFrame.from_records(records)


def _physical_regime(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _physical_value(
    payload: dict[str, Any],
    physical_regime: dict[str, Any],
    flat_key: str,
    nested_key: str,
    default: Any,
) -> Any:
    value = payload.get(flat_key)
    if value is not None:
        return value
    value = physical_regime.get(nested_key)
    if value is not None:
        return value
    return payload.get(nested_key, default)


def _best_relative_path(candidate: Path, raw_dir: Path) -> str:
    if candidate.exists():
        try:
            return str(candidate.resolve().relative_to(raw_dir.resolve())).replace("\\", "/")
        except Exception:
            return str(candidate.resolve())
    return str(candidate)


def _finalize_canonical_frame(frame: pd.DataFrame, dataset_config: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("Canonical metadata is empty.")

    required_defaults = {
        "seed": None,
        "freeze_version": "unversioned",
        "artifact_wrapper": False,
        "dataset_split": None,
        "attack_strength": BENIGN_REGIME_VALUE,
        "policy_message_source": "none",
        "message_variant_id": "none",
        "num_chunks": 0,
        "chunk_strategy": BENIGN_REGIME_VALUE,
        "avg_chunk_len": 0.0,
        "raw_injected_text": None,
        "message_length_chars": None,
        "benign_confounder_family": "none",
        "pair_id": None,
        "triad_id": None,
        "pdf_role": "unknown",
        "target_message_type": "none",
        "target_attack_family": "none",
        "target_benign_confounder_family": "none",
        "target_physical_attack_family": "none",
        "target_physical_attack_strength": "none",
        "target_physical_structural_regime": "none",
        "target_physical_spatial_regime": "none",
        "target_physical_rendering_regime": "none",
        "target_physical_artifact_wrapper": False,
        "confounder_physical_attack_family": "none",
        "confounder_physical_attack_strength": "none",
        "confounder_physical_structural_regime": "none",
        "confounder_physical_spatial_regime": "none",
        "confounder_physical_rendering_regime": "none",
        "confounder_physical_artifact_wrapper": False,
    }
    for column, default in required_defaults.items():
        if column not in frame.columns:
            frame[column] = default

    for column in REQUIRED_METADATA_COLUMNS:
        if column not in frame.columns:
            raise ValueError(f"Canonical metadata is missing required column '{column}'.")

    finalized = frame.copy()
    finalized["label"] = finalized["label"].astype(int)
    finalized["artifact_wrapper"] = finalized["artifact_wrapper"].map(coerce_bool)
    finalized["file_path"] = finalized["file_path"].astype(str)
    finalized["split_group"] = finalized["split_group"].astype(str)
    finalized["base_pdf_id"] = finalized["base_pdf_id"].astype(str)
    finalized["pdf_id"] = finalized["pdf_id"].astype(str)
    finalized["pair_id"] = finalized["pair_id"].fillna(finalized["pdf_id"]).astype(str)
    finalized["triad_id"] = finalized["triad_id"].fillna(finalized["pair_id"]).astype(str)
    finalized["pdf_role"] = finalized["pdf_role"].fillna("unknown").astype(str)
    benign_value = dataset_config.get("benign_regime_value", BENIGN_REGIME_VALUE)
    finalized["message_variant_id"] = finalized["message_variant_id"].fillna("none").astype(str)
    finalized["policy_message_source"] = finalized["policy_message_source"].fillna("none").astype(str)
    finalized["chunk_strategy"] = finalized["chunk_strategy"].fillna(benign_value).astype(str)
    finalized["num_chunks"] = finalized["num_chunks"].fillna(0).astype(int)
    finalized["avg_chunk_len"] = finalized["avg_chunk_len"].fillna(0.0).astype(float)
    finalized["benign_confounder_family"] = finalized["benign_confounder_family"].fillna("none").astype(str)
    finalized["target_message_type"] = finalized["target_message_type"].fillna("none").astype(str)
    finalized["target_attack_family"] = finalized["target_attack_family"].fillna("none").astype(str)
    finalized["target_benign_confounder_family"] = (
        finalized["target_benign_confounder_family"].fillna("none").astype(str)
    )
    for column in [
        "target_physical_attack_family",
        "target_physical_attack_strength",
        "target_physical_structural_regime",
        "target_physical_spatial_regime",
        "target_physical_rendering_regime",
        "confounder_physical_attack_family",
        "confounder_physical_attack_strength",
        "confounder_physical_structural_regime",
        "confounder_physical_spatial_regime",
        "confounder_physical_rendering_regime",
    ]:
        finalized[column] = finalized[column].fillna("none").astype(str)
    finalized["target_physical_artifact_wrapper"] = finalized["target_physical_artifact_wrapper"].map(coerce_bool)
    finalized["confounder_physical_artifact_wrapper"] = finalized["confounder_physical_artifact_wrapper"].map(coerce_bool)
    finalized["confounder_physical_attack_family"] = (
        finalized["confounder_physical_attack_family"].fillna("none").astype(str)
    )
    finalized["confounder_physical_structural_regime"] = (
        finalized["confounder_physical_structural_regime"].fillna("none").astype(str)
    )
    finalized["confounder_physical_spatial_regime"] = (
        finalized["confounder_physical_spatial_regime"].fillna("none").astype(str)
    )

    finalized = _backfill_physical_regimes_from_injected_rows(finalized)

    for column in [
        "source_type",
        "spatial_regime",
        "rendering_regime",
        "structural_regime",
        "message_type",
        "attack_family",
        "attack_strength",
    ]:
        finalized[column] = finalized[column].fillna(benign_value).astype(str)

    finalized = finalized.sort_values("pdf_id").reset_index(drop=True)
    return finalized


def _backfill_physical_regimes_from_injected_rows(frame: pd.DataFrame) -> pd.DataFrame:
    group_column = "triad_id" if "triad_id" in frame.columns else "pair_id"
    if group_column not in frame.columns or "pdf_role" not in frame.columns:
        return frame

    target_columns = [
        ("target_physical_attack_family", "attack_family", "confounder_physical_attack_family"),
        ("target_physical_attack_strength", "attack_strength", "confounder_physical_attack_strength"),
        ("target_physical_structural_regime", "structural_regime", "confounder_physical_structural_regime"),
        ("target_physical_spatial_regime", "spatial_regime", "confounder_physical_spatial_regime"),
        ("target_physical_rendering_regime", "rendering_regime", "confounder_physical_rendering_regime"),
        ("target_physical_artifact_wrapper", "artifact_wrapper", "confounder_physical_artifact_wrapper"),
    ]
    injected = frame[frame["pdf_role"].astype(str) == "injected_attack"].copy()
    if injected.empty:
        return frame

    injected_by_group = injected.drop_duplicates(subset=[group_column]).set_index(group_column)
    for index, row in frame.iterrows():
        group_id = row.get(group_column)
        if group_id not in injected_by_group.index:
            continue
        injected_row = injected_by_group.loc[group_id]
        is_confounder = str(row.get("pdf_role")) == "benign_confounder"
        has_partial_confounder_physical = is_confounder and any(
            _is_missing_regime_value(row.get(confounder_column))
            for _, _, confounder_column in target_columns
        )
        for target_column, injected_column, confounder_column in target_columns:
            target_value = row.get(target_column)
            if _is_missing_regime_value(target_value):
                frame.at[index, target_column] = injected_row.get(injected_column)
            if has_partial_confounder_physical or (is_confounder and _is_missing_regime_value(row.get(confounder_column))):
                frame.at[index, confounder_column] = frame.at[index, target_column]

    frame["target_physical_artifact_wrapper"] = frame["target_physical_artifact_wrapper"].map(coerce_bool)
    frame["confounder_physical_artifact_wrapper"] = frame["confounder_physical_artifact_wrapper"].map(coerce_bool)
    return frame


def _is_missing_regime_value(value: Any) -> bool:
    return value is None or str(value).strip().lower() in {"", "none", "nan"}
