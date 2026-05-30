from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.load_metadata import load_dataset_config
from src.eval.metrics import compute_classification_metrics, select_best_threshold
from src.features.normalize import build_logreg_preprocessor, ordered_feature_frame, select_feature_columns
from src.features.schema import FEATURE_GROUPS
from src.models.common import (
    load_extractor_config,
    load_training_config,
    load_training_tables,
    merge_features_and_labels,
    persist_artifact,
    split_merged_frame,
)
from src.models.text_preprocessing import (
    audit_text_feature_weights,
    build_text_preprocessing_config,
)
from src.parsers.pdf_text import extract_pypdf_text


TEXT_COLUMN = "pypdf_text"


def train_hybrid_model(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: dict[str, Any],
    training_config: dict[str, Any],
    dataset_config: dict[str, Any],
    *,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = merge_features_and_labels(features, labels)
    split_frames = split_merged_frame(merged, splits)
    effective_drop_feature_groups = list(training_config.get("drop_feature_groups", []) or []) + list(drop_feature_groups or [])
    effective_drop_feature_columns = list(training_config.get("drop_feature_columns", []) or []) + list(drop_feature_columns or [])
    feature_columns = select_feature_columns(
        effective_drop_feature_groups,
        effective_drop_feature_columns,
    )
    threshold = float(training_config.get("threshold", 0.5))
    threshold_selection = str(training_config.get("threshold_selection", "fixed")).strip().lower()
    hybrid_cfg = training_config.get("hybrid", {}) or {}
    text_cfg = training_config.get("text_tfidf", {}) or hybrid_cfg.get("text_tfidf", {}) or {}
    preprocessing = build_text_preprocessing_config(text_cfg)
    text_cache: dict[str, str] = {}

    train_frame = split_frames["train"]
    val_frame = split_frames["val"]
    test_frame = split_frames["test"]

    x_train = _build_hybrid_frame(
        train_frame,
        feature_columns,
        dataset_config,
        preprocessing,
        cache=text_cache,
        split_name="train",
    )
    y_train = train_frame["label"].astype(int).to_numpy()
    x_val = _build_hybrid_frame(
        val_frame,
        feature_columns,
        dataset_config,
        preprocessing,
        cache=text_cache,
        split_name="val",
    )
    y_val = val_frame["label"].astype(int).to_numpy()
    x_test = _build_hybrid_frame(
        test_frame,
        feature_columns,
        dataset_config,
        preprocessing,
        cache=text_cache,
        split_name="test",
    )
    y_test = test_frame["label"].astype(int).to_numpy()

    c_values = [float(value) for value in hybrid_cfg.get("c_values", text_cfg.get("c_values", [1.0]))]
    max_iter = int(hybrid_cfg.get("max_iter", text_cfg.get("max_iter", 4000)))
    class_weight = hybrid_cfg.get("class_weight", text_cfg.get("class_weight", "balanced"))
    solver = str(hybrid_cfg.get("solver", text_cfg.get("solver", "liblinear")))
    word_ngram_range = tuple(int(value) for value in text_cfg.get("word_ngram_range", [1, 2]))
    char_ngram_range = tuple(int(value) for value in text_cfg.get("char_ngram_range", [3, 5]))
    max_features_word = int(text_cfg.get("max_features_word", 50000))
    max_features_char = int(text_cfg.get("max_features_char", 50000))
    min_df = int(text_cfg.get("min_df", 1))
    max_df = float(text_cfg.get("max_df", 1.0))

    best_bundle: dict[str, Any] | None = None
    best_score = float("-inf")
    for c_value in c_values:
        pipeline = _build_pipeline(
            feature_columns=feature_columns,
            c_value=c_value,
            max_iter=max_iter,
            class_weight=class_weight,
            solver=solver,
            word_ngram_range=word_ngram_range,
            char_ngram_range=char_ngram_range,
            max_features_word=max_features_word,
            max_features_char=max_features_char,
            min_df=min_df,
            max_df=max_df,
        )
        pipeline.fit(x_train, y_train)
        val_scores = pipeline.predict_proba(x_val)[:, 1]
        selected_threshold = (
            select_best_threshold(y_val, val_scores, metric="f1")["threshold"]
            if threshold_selection == "best_f1_on_val"
            else threshold
        )
        val_metrics = compute_classification_metrics(y_val, val_scores, threshold=float(selected_threshold))
        selection_score = float(val_metrics["f1"])
        if selection_score > best_score:
            best_score = selection_score
            best_bundle = {
                "c_value": c_value,
                "val_metrics": val_metrics,
                "threshold": float(selected_threshold),
            }

    if best_bundle is None:
        raise RuntimeError("Failed to select a hybrid logistic regression configuration.")

    train_val_frame = pd.concat([train_frame, val_frame], ignore_index=True)
    x_train_val = _build_hybrid_frame(
        train_val_frame,
        feature_columns,
        dataset_config,
        preprocessing,
        cache=text_cache,
        split_name="train_val",
    )
    y_train_val = train_val_frame["label"].astype(int).to_numpy()

    final_pipeline = _build_pipeline(
        feature_columns=feature_columns,
        c_value=float(best_bundle["c_value"]),
        max_iter=max_iter,
        class_weight=class_weight,
        solver=solver,
        word_ngram_range=word_ngram_range,
        char_ngram_range=char_ngram_range,
        max_features_word=max_features_word,
        max_features_char=max_features_char,
        min_df=min_df,
        max_df=max_df,
    )
    final_pipeline.fit(x_train_val, y_train_val)

    final_threshold = float(best_bundle["threshold"])
    train_scores = final_pipeline.predict_proba(x_train_val)[:, 1]
    test_scores = final_pipeline.predict_proba(x_test)[:, 1]
    train_metrics = compute_classification_metrics(y_train_val, train_scores, threshold=final_threshold)
    test_metrics = compute_classification_metrics(y_test, test_scores, threshold=final_threshold)
    feature_importance = _top_hybrid_feature_importance(final_pipeline)
    feature_weight_audit = audit_text_feature_weights(
        _text_only_audit_pipeline(final_pipeline),
        known_wrappers=[
            *preprocessing["known_benchmark_wrappers"],
            *preprocessing["synthetic_phrase_markers"],
        ],
    )

    artifact = {
        "model_name": "hybrid",
        "pipeline": final_pipeline,
        "feature_columns": feature_columns,
        "feature_groups": FEATURE_GROUPS,
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "threshold": final_threshold,
        "threshold_selection": threshold_selection,
        "feature_importance": feature_importance,
        "feature_weight_audit": feature_weight_audit,
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "extractor_config": load_extractor_config(training_config),
        "dataset_config": dataset_config,
        "text_preprocessing": preprocessing,
        "text_source": "pypdf_page_extract_text",
        "numeric_feature_source": "non_forbidden_feature_columns",
        "forbidden_sources": ["raw_pdf_syntax", "pdf_metadata", "raw_injected_text"],
        "training_config": training_config,
    }
    metrics = {
        "model_name": "hybrid",
        "text_source": "pypdf_page_extract_text",
        "numeric_feature_source": "non_forbidden_feature_columns",
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "train_metrics": train_metrics,
        "val_metrics": best_bundle["val_metrics"],
        "test_metrics": test_metrics,
        "feature_columns": feature_columns,
        "empty_text_counts": {
            "train": int((x_train[TEXT_COLUMN].astype(str) == "").sum()),
            "val": int((x_val[TEXT_COLUMN].astype(str) == "").sum()),
            "test": int((x_test[TEXT_COLUMN].astype(str) == "").sum()),
        },
        "feature_importance": feature_importance,
        "feature_weight_audit": feature_weight_audit,
        "text_preprocessing": preprocessing,
    }
    return artifact, metrics


def train_hybrid_from_config(
    config: str | Path | dict[str, Any],
    *,
    persist: bool = True,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    training_config = load_training_config(config)
    if not training_config.get("dataset_config"):
        raise ValueError("Hybrid training requires dataset_config for pypdf text extraction.")
    dataset_config = load_dataset_config(training_config["dataset_config"])
    features, labels, splits = load_training_tables(training_config)
    artifact, metrics = train_hybrid_model(
        features,
        labels,
        splits,
        training_config,
        dataset_config,
        drop_feature_groups=drop_feature_groups,
        drop_feature_columns=drop_feature_columns,
    )
    if persist:
        paths = persist_artifact(
            artifact,
            output_model_path=training_config["output_model_path"],
            output_metrics_path=training_config["output_metrics_path"],
            metrics_payload=metrics,
        )
        metrics.update(paths)
    return artifact, metrics


def _build_pipeline(
    *,
    feature_columns: list[str],
    c_value: float,
    max_iter: int,
    class_weight: Any,
    solver: str,
    word_ngram_range: tuple[int, int],
    char_ngram_range: tuple[int, int],
    max_features_word: int,
    max_features_char: int,
    min_df: int,
    max_df: float,
):
    from sklearn.compose import ColumnTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    text_features = FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=word_ngram_range,
                    lowercase=True,
                    strip_accents="unicode",
                    max_features=max_features_word,
                    min_df=min_df,
                    max_df=max_df,
                    sublinear_tf=True,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=char_ngram_range,
                    lowercase=True,
                    strip_accents="unicode",
                    max_features=max_features_char,
                    min_df=min_df,
                    max_df=max_df,
                    sublinear_tf=True,
                ),
            ),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("text", text_features, TEXT_COLUMN),
            ("numeric", build_logreg_preprocessor(), feature_columns),
        ],
        remainder="drop",
    )
    return Pipeline(
        steps=[
            ("features", preprocessor),
            (
                "classifier",
                LogisticRegression(
                    C=c_value,
                    max_iter=max_iter,
                    class_weight=class_weight,
                    solver=solver,
                ),
            ),
        ]
    )


def _build_hybrid_frame(
    frame: pd.DataFrame,
    feature_columns: list[str],
    dataset_config: dict[str, Any],
    preprocessing: dict[str, Any],
    *,
    cache: dict[str, str] | None = None,
    split_name: str = "split",
) -> pd.DataFrame:
    from src.models.text_preprocessing import apply_text_preprocessing

    output = ordered_feature_frame(frame, feature_columns)
    texts: list[str] = []
    paths = frame["file_path"].astype(str).tolist()
    total = len(paths)
    for index, file_path in enumerate(paths, start=1):
        if cache is not None and file_path in cache:
            texts.append(cache[file_path])
            continue
        text = apply_text_preprocessing(extract_pypdf_text(file_path, dataset_config), preprocessing)
        if cache is not None:
            cache[file_path] = text
        texts.append(text)
        if index == 1 or index == total or index % 1000 == 0:
            print(f"[hybrid] extracted {split_name} {index}/{total}", flush=True)
    output.insert(0, TEXT_COLUMN, texts)
    return output


def _top_hybrid_feature_importance(pipeline: Any, limit: int = 200) -> dict[str, float]:
    classifier = pipeline.named_steps["classifier"]
    features = pipeline.named_steps["features"]
    if not hasattr(classifier, "coef_") or not hasattr(features, "get_feature_names_out"):
        return {}
    names = features.get_feature_names_out()
    weights = np.asarray(classifier.coef_[0], dtype=float)
    ranking = np.argsort(np.abs(weights))[::-1][:limit]
    return {str(names[index]): float(abs(weights[index])) for index in ranking}


def _text_only_audit_pipeline(pipeline: Any) -> Any:
    from sklearn.pipeline import Pipeline

    class _TextFeatureView:
        def __init__(self, features: Any) -> None:
            self._features = features

        def get_feature_names_out(self) -> Any:
            names = self._features.get_feature_names_out()
            return np.asarray([name for name in names if str(name).startswith("text__")], dtype=object)

    class _TextClassifierView:
        def __init__(self, classifier: Any, features: Any) -> None:
            names = features.get_feature_names_out()
            mask = np.asarray([str(name).startswith("text__") for name in names], dtype=bool)
            self.coef_ = np.asarray(classifier.coef_)[:, mask]

    features = pipeline.named_steps["features"]
    classifier = pipeline.named_steps["classifier"]
    return Pipeline(
        steps=[
            ("features", _TextFeatureView(features)),
            ("classifier", _TextClassifierView(classifier, features)),
        ]
    )
