from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.common import resolve_path
from src.features.normalize import ordered_feature_frame
from src.models.text_preprocessing import apply_text_preprocessing
from src.parsers.pdf_features import extract_pdf_features
from src.parsers.pdf_text import extract_pypdf_text

HYBRID_TEXT_COLUMN = "pypdf_text"


def load_model_artifact(path_like: str | Path) -> dict[str, Any]:
    path = resolve_path(path_like)
    with path.open("rb") as handle:
        return pickle.load(handle)


def predict_scores(
    artifact: dict[str, Any],
    feature_frame: pd.DataFrame,
    *,
    text_preprocessing_override: dict[str, Any] | None = None,
) -> np.ndarray:
    if artifact.get("model_name") == "text_tfidf":
        if "file_path" not in feature_frame.columns:
            raise ValueError("Text TF-IDF artifacts require a feature frame with a file_path column.")
        dataset_config = artifact.get("dataset_config", {}) or {}
        preprocessing = text_preprocessing_override or artifact.get("text_preprocessing", {}) or {}
        texts = [
            apply_text_preprocessing(extract_pypdf_text(file_path, dataset_config), preprocessing)
            for file_path in feature_frame["file_path"].astype(str).tolist()
        ]
        return artifact["pipeline"].predict_proba(texts)[:, 1]
    if artifact.get("model_name") == "hybrid":
        hybrid_frame = _build_hybrid_feature_frame(
            artifact,
            feature_frame,
            text_preprocessing_override=text_preprocessing_override,
        )
        return artifact["pipeline"].predict_proba(hybrid_frame)[:, 1]
    x = ordered_feature_frame(feature_frame, artifact["feature_columns"])
    transformed = artifact["preprocessor"].transform(x)
    return artifact["model"].predict_proba(transformed)[:, 1]


def top_signals(artifact: dict[str, Any], feature_frame: pd.DataFrame, top_k: int = 3) -> list[str]:
    if artifact.get("model_name") == "text_tfidf":
        return [
            feature_name
            for feature_name, _ in sorted(
                artifact.get("feature_importance", {}).items(),
                key=lambda item: item[1],
                reverse=True,
            )[:top_k]
        ]
    if artifact.get("model_name") == "hybrid":
        hybrid_frame = _build_hybrid_feature_frame(artifact, feature_frame)
        pipeline = artifact["pipeline"]
        features = pipeline.named_steps["features"]
        model = pipeline.named_steps["classifier"]
        transformed = features.transform(hybrid_frame)
        row = transformed[0]
        if hasattr(row, "toarray"):
            row = row.toarray()[0]
        row = np.asarray(row, dtype=float)
        if hasattr(model, "coef_"):
            contribution = row * np.asarray(model.coef_[0], dtype=float)
            ranking = np.argsort(np.abs(contribution))[::-1]
            names = features.get_feature_names_out()
            return [str(names[index]) for index in ranking[:top_k]]
        return [
            feature_name
            for feature_name, _ in sorted(
                artifact.get("feature_importance", {}).items(),
                key=lambda item: item[1],
                reverse=True,
            )[:top_k]
        ]
    x = ordered_feature_frame(feature_frame, artifact["feature_columns"])
    transformed = artifact["preprocessor"].transform(x)
    row = transformed[0]
    if hasattr(row, "toarray"):
        row = row.toarray()[0]
    row = np.asarray(row, dtype=float)

    model = artifact["model"]
    if hasattr(model, "coef_"):
        contribution = row * np.asarray(model.coef_[0], dtype=float)
        ranking = np.argsort(np.abs(contribution))[::-1]
    elif hasattr(model, "feature_importances_"):
        contribution = np.abs(row) * np.asarray(model.feature_importances_, dtype=float)
        ranking = np.argsort(contribution)[::-1]
    else:
        importance = artifact.get("feature_importance", {})
        ranking = [
            artifact["feature_columns"].index(name)
            for name, _ in sorted(importance.items(), key=lambda item: item[1], reverse=True)
        ]

    return [artifact["feature_columns"][index] for index in ranking[:top_k]]


def infer_pdf(model_path: str | Path, pdf_path: str | Path) -> dict[str, Any]:
    artifact = load_model_artifact(model_path)
    if artifact.get("model_name") == "text_tfidf":
        feature_frame = pd.DataFrame([{"pdf_id": Path(pdf_path).stem, "file_path": str(pdf_path)}])
        score = float(predict_scores(artifact, feature_frame)[0])
        threshold = float(artifact.get("threshold", 0.5))
        return {
            "pdf_id": Path(pdf_path).stem,
            "risk_score": score,
            "prediction": int(score >= threshold),
            "top_signals": top_signals(artifact, feature_frame),
            "parse_errors": 0,
        }
    extraction = extract_pdf_features(pdf_path, artifact.get("extractor_config", {}))
    feature_frame = pd.DataFrame(
        [{"pdf_id": Path(pdf_path).stem, "file_path": str(pdf_path), **extraction["features"]}]
    )
    score = float(predict_scores(artifact, feature_frame)[0])
    threshold = float(artifact.get("threshold", 0.5))
    return {
        "pdf_id": Path(pdf_path).stem,
        "risk_score": score,
        "prediction": int(score >= threshold),
        "top_signals": top_signals(artifact, feature_frame),
        "parse_errors": int(extraction["parse_errors"]),
    }


def _build_hybrid_feature_frame(
    artifact: dict[str, Any],
    feature_frame: pd.DataFrame,
    *,
    text_preprocessing_override: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if "file_path" not in feature_frame.columns:
        raise ValueError("Hybrid artifacts require a feature frame with a file_path column.")
    dataset_config = artifact.get("dataset_config", {}) or {}
    preprocessing = text_preprocessing_override or artifact.get("text_preprocessing", {}) or {}
    x = ordered_feature_frame(feature_frame, artifact["feature_columns"])
    texts = [
        apply_text_preprocessing(extract_pypdf_text(file_path, dataset_config), preprocessing)
        for file_path in feature_frame["file_path"].astype(str).tolist()
    ]
    x.insert(0, HYBRID_TEXT_COLUMN, texts)
    return x
