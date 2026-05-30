from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

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


def train_logreg_model(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: dict[str, Any],
    training_config: dict[str, Any],
    *,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

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

    train_frame = split_frames["train"]
    val_frame = split_frames["val"]
    test_frame = split_frames["test"]

    x_train = ordered_feature_frame(train_frame, feature_columns)
    y_train = train_frame["label"].astype(int).to_numpy()
    x_val = ordered_feature_frame(val_frame, feature_columns)
    y_val = val_frame["label"].astype(int).to_numpy()
    x_test = ordered_feature_frame(test_frame, feature_columns)
    y_test = test_frame["label"].astype(int).to_numpy()

    logreg_cfg = training_config.get("logreg", {})
    c_values = [float(value) for value in logreg_cfg.get("c_values", [1.0])]
    max_iter = int(logreg_cfg.get("max_iter", 4000))
    class_weight = logreg_cfg.get("class_weight")
    solver = str(logreg_cfg.get("solver", "liblinear"))

    best_bundle: dict[str, Any] | None = None
    best_score = float("-inf")

    for c_value in c_values:
        pipeline = Pipeline(
            steps=[
                ("preprocessor", build_logreg_preprocessor()),
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
        raise RuntimeError("Failed to select a logistic regression configuration.")

    train_val_frame = pd.concat([train_frame, val_frame], ignore_index=True)
    x_train_val = ordered_feature_frame(train_val_frame, feature_columns)
    y_train_val = train_val_frame["label"].astype(int).to_numpy()

    final_pipeline = Pipeline(
        steps=[
            ("preprocessor", build_logreg_preprocessor()),
            (
                "classifier",
                LogisticRegression(
                    C=float(best_bundle["c_value"]),
                    max_iter=max_iter,
                    class_weight=class_weight,
                    solver=solver,
                ),
            ),
        ]
    )
    final_pipeline.fit(x_train_val, y_train_val)

    train_scores = final_pipeline.predict_proba(x_train_val)[:, 1]
    test_scores = final_pipeline.predict_proba(x_test)[:, 1]
    final_threshold = float(best_bundle["threshold"])
    train_metrics = compute_classification_metrics(y_train_val, train_scores, threshold=final_threshold)
    test_metrics = compute_classification_metrics(y_test, test_scores, threshold=final_threshold)

    preprocessor = final_pipeline.named_steps["preprocessor"]
    model = final_pipeline.named_steps["classifier"]
    coefficients = model.coef_[0].tolist()
    feature_importance = {
        column: float(abs(weight)) for column, weight in zip(feature_columns, coefficients)
    }

    artifact = {
        "model_name": "logreg",
        "feature_columns": feature_columns,
        "feature_groups": FEATURE_GROUPS,
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "preprocessor": preprocessor,
        "model": model,
        "threshold": final_threshold,
        "threshold_selection": threshold_selection,
        "feature_importance": feature_importance,
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "extractor_config": load_extractor_config(training_config),
        "training_config": training_config,
    }
    metrics = {
        "model_name": "logreg",
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "selected_params": {"C": float(best_bundle["c_value"])},
        "selected_threshold": final_threshold,
        "train_metrics": train_metrics,
        "val_metrics": best_bundle["val_metrics"],
        "test_metrics": test_metrics,
        "feature_columns": feature_columns,
    }
    return artifact, metrics


def train_logreg_from_config(
    config: str | Path | dict[str, Any],
    *,
    persist: bool = True,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    training_config = load_training_config(config)
    features, labels, splits = load_training_tables(training_config)
    artifact, metrics = train_logreg_model(
        features,
        labels,
        splits,
        training_config,
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
