from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.common import load_yaml_config, resolve_path
from src.data.build_splits import load_splits
from src.data.load_metadata import load_dataset_config
from src.eval.metrics import compute_classification_metrics, select_best_threshold
from src.models.common import persist_artifact
from src.models.text_preprocessing import (
    audit_text_feature_weights,
    build_text_preprocessing_config,
)
from src.parsers.pdf_text import extract_pypdf_text


def train_text_tfidf_model(
    labels: pd.DataFrame,
    splits: dict[str, Any],
    training_config: dict[str, Any],
    dataset_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    split_frames = _split_label_frame(labels, splits)
    threshold = float(training_config.get("threshold", 0.5))
    threshold_selection = str(training_config.get("threshold_selection", "fixed")).strip().lower()

    train_frame = split_frames["train"]
    val_frame = split_frames["val"]
    test_frame = split_frames["test"]
    text_cfg = training_config.get("text_tfidf", {}) or {}
    preprocessing = build_text_preprocessing_config(text_cfg)
    text_cache: dict[str, str] = {}
    train_texts = _extract_texts(train_frame, dataset_config, preprocessing, cache=text_cache, split_name="train")
    val_texts = _extract_texts(val_frame, dataset_config, preprocessing, cache=text_cache, split_name="val")
    test_texts = _extract_texts(test_frame, dataset_config, preprocessing, cache=text_cache, split_name="test")
    y_train = train_frame["label"].astype(int).to_numpy()
    y_val = val_frame["label"].astype(int).to_numpy()
    y_test = test_frame["label"].astype(int).to_numpy()

    c_values = [float(value) for value in text_cfg.get("c_values", [1.0])]
    max_iter = int(text_cfg.get("max_iter", 4000))
    class_weight = text_cfg.get("class_weight", "balanced")
    solver = str(text_cfg.get("solver", "liblinear"))
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
        pipeline.fit(train_texts, y_train)
        val_scores = pipeline.predict_proba(val_texts)[:, 1]
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
        raise RuntimeError("Failed to select a text TF-IDF configuration.")

    train_val_frame = pd.concat([train_frame, val_frame], ignore_index=True)
    train_val_texts = _extract_texts(
        train_val_frame,
        dataset_config,
        preprocessing,
        cache=text_cache,
        split_name="train_val",
    )
    y_train_val = train_val_frame["label"].astype(int).to_numpy()
    final_pipeline = _build_pipeline(
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
    final_pipeline.fit(train_val_texts, y_train_val)

    final_threshold = float(best_bundle["threshold"])
    train_scores = final_pipeline.predict_proba(train_val_texts)[:, 1]
    test_scores = final_pipeline.predict_proba(test_texts)[:, 1]
    train_metrics = compute_classification_metrics(y_train_val, train_scores, threshold=final_threshold)
    test_metrics = compute_classification_metrics(y_test, test_scores, threshold=final_threshold)
    feature_weight_audit = audit_text_feature_weights(
        final_pipeline,
        known_wrappers=[
            *preprocessing["known_benchmark_wrappers"],
            *preprocessing["synthetic_phrase_markers"],
        ],
    )
    feature_importance = _top_text_feature_importance(final_pipeline)

    artifact = {
        "model_name": "text_tfidf",
        "pipeline": final_pipeline,
        "threshold": final_threshold,
        "threshold_selection": threshold_selection,
        "feature_importance": feature_importance,
        "feature_weight_audit": feature_weight_audit,
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "dataset_config": dataset_config,
        "text_preprocessing": preprocessing,
        "text_source": "pypdf_page_extract_text",
        "forbidden_sources": ["raw_pdf_syntax", "pdf_metadata", "raw_injected_text"],
        "training_config": training_config,
    }
    metrics = {
        "model_name": "text_tfidf",
        "text_source": "pypdf_page_extract_text",
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "train_metrics": train_metrics,
        "val_metrics": best_bundle["val_metrics"],
        "test_metrics": test_metrics,
        "empty_text_counts": {
            "train": int(sum(1 for text in train_texts if not text)),
            "val": int(sum(1 for text in val_texts if not text)),
            "test": int(sum(1 for text in test_texts if not text)),
        },
        "feature_importance": feature_importance,
        "feature_weight_audit": feature_weight_audit,
        "text_preprocessing": preprocessing,
    }
    return artifact, metrics


def train_text_tfidf_from_config(
    config: str | Path | dict[str, Any],
    *,
    persist: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    training_config = load_yaml_config(config) if not isinstance(config, dict) else config
    dataset_config = load_dataset_config(training_config["dataset_config"])
    labels = pd.read_parquet(resolve_path(training_config["labels_path"]))
    splits = load_splits(resolve_path(training_config["splits_path"]))
    artifact, metrics = train_text_tfidf_model(labels, splits, training_config, dataset_config)
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
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    return Pipeline(
        steps=[
            (
                "features",
                FeatureUnion(
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
                ),
            ),
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


def _split_label_frame(labels: pd.DataFrame, splits: dict[str, Any]) -> dict[str, pd.DataFrame]:
    output = {}
    for split_name in ["train", "val", "test"]:
        ids = splits.get(f"{split_name}_ids", [])
        frame = labels[labels["pdf_id"].isin(ids)].copy().reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"Split '{split_name}' is empty.")
        output[split_name] = frame
    return output


def _extract_texts(
    frame: pd.DataFrame,
    dataset_config: dict[str, Any],
    preprocessing: dict[str, Any] | None = None,
    *,
    cache: dict[str, str] | None = None,
    split_name: str = "split",
) -> list[str]:
    from src.models.text_preprocessing import apply_text_preprocessing

    output: list[str] = []
    paths = frame["file_path"].astype(str).tolist()
    total = len(paths)
    for index, file_path in enumerate(paths, start=1):
        if cache is not None and file_path in cache:
            output.append(cache[file_path])
            continue
        text = apply_text_preprocessing(extract_pypdf_text(file_path, dataset_config), preprocessing)
        if cache is not None:
            cache[file_path] = text
        output.append(text)
        if index == 1 or index == total or index % 1000 == 0:
            print(f"[text-tfidf] extracted {split_name} {index}/{total}", flush=True)
    return output


def _top_text_feature_importance(pipeline: Any, limit: int = 200) -> dict[str, float]:
    classifier = pipeline.named_steps["classifier"]
    features = pipeline.named_steps["features"]
    if not hasattr(classifier, "coef_") or not hasattr(features, "get_feature_names_out"):
        return {}
    names = features.get_feature_names_out()
    weights = np.asarray(classifier.coef_[0], dtype=float)
    ranking = np.argsort(np.abs(weights))[::-1][:limit]
    return {str(names[index]): float(abs(weights[index])) for index in ranking}
