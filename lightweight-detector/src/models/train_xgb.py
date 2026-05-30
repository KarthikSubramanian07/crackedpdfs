from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.eval.metrics import compute_classification_metrics, select_best_threshold
from src.features.normalize import build_tree_preprocessor, ordered_feature_frame, select_feature_columns
from src.features.schema import FEATURE_GROUPS
from src.models.common import (
    load_extractor_config,
    load_training_config,
    load_training_tables,
    merge_features_and_labels,
    persist_artifact,
    split_merged_frame,
)


def train_xgb_model(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: dict[str, Any],
    training_config: dict[str, Any],
    *,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from xgboost import XGBClassifier
    except Exception as exc:
        raise RuntimeError("xgboost is required for the xgb baseline.") from exc

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

    xgb_cfg = training_config.get("xgb", {})
    base_n_estimators = int(xgb_cfg.get("n_estimators", 400))
    base_kwargs = {
        "n_estimators": base_n_estimators,
        "max_depth": int(xgb_cfg.get("max_depth", 4)),
        "learning_rate": float(xgb_cfg.get("learning_rate", 0.05)),
        "subsample": float(xgb_cfg.get("subsample", 0.9)),
        "colsample_bytree": float(xgb_cfg.get("colsample_bytree", 0.9)),
        "reg_lambda": float(xgb_cfg.get("reg_lambda", 1.0)),
        "min_child_weight": float(xgb_cfg.get("min_child_weight", 1.0)),
        "random_state": int(training_config.get("random_state", 42)),
        "objective": "binary:logistic",
        "eval_metric": str(xgb_cfg.get("eval_metric", "logloss")),
    }
    early_stopping_rounds = int(xgb_cfg.get("early_stopping_rounds", 25))

    preprocessor = build_tree_preprocessor()
    x_train_arr = preprocessor.fit_transform(x_train)
    x_val_arr = preprocessor.transform(x_val)

    warm_kwargs = dict(base_kwargs)
    fit_kwargs = {"verbose": False}
    if len(x_val_arr):
        warm_kwargs["early_stopping_rounds"] = early_stopping_rounds
        fit_kwargs["eval_set"] = [(x_val_arr, y_val)]
    warm_model = XGBClassifier(**warm_kwargs)
    warm_model.fit(x_train_arr, y_train, **fit_kwargs)

    val_scores = warm_model.predict_proba(x_val_arr)[:, 1]
    selected_threshold = (
        select_best_threshold(y_val, val_scores, metric="f1")["threshold"]
        if threshold_selection == "best_f1_on_val"
        else {"threshold": threshold}
    )
    final_threshold = float(
        selected_threshold["threshold"] if isinstance(selected_threshold, dict) else selected_threshold
    )
    val_metrics = compute_classification_metrics(y_val, val_scores, threshold=final_threshold)
    best_iteration = getattr(warm_model, "best_iteration", None)
    final_n_estimators = base_n_estimators if best_iteration is None else max(1, int(best_iteration) + 1)

    train_val_frame = pd.concat([train_frame, val_frame], ignore_index=True)
    x_train_val = ordered_feature_frame(train_val_frame, feature_columns)
    y_train_val = train_val_frame["label"].astype(int).to_numpy()

    final_preprocessor = build_tree_preprocessor()
    x_train_val_arr = final_preprocessor.fit_transform(x_train_val)
    x_test_arr = final_preprocessor.transform(x_test)

    final_model = XGBClassifier(**{**base_kwargs, "n_estimators": final_n_estimators})
    final_model.fit(x_train_val_arr, y_train_val, verbose=False)

    train_scores = final_model.predict_proba(x_train_val_arr)[:, 1]
    test_scores = final_model.predict_proba(x_test_arr)[:, 1]
    train_metrics = compute_classification_metrics(y_train_val, train_scores, threshold=final_threshold)
    test_metrics = compute_classification_metrics(y_test, test_scores, threshold=final_threshold)

    importance_values = getattr(final_model, "feature_importances_", None)
    if importance_values is None:
        importance_values = [0.0] * len(feature_columns)
    feature_importance = {
        column: float(value) for column, value in zip(feature_columns, importance_values)
    }

    artifact = {
        "model_name": "xgb",
        "feature_columns": feature_columns,
        "feature_groups": FEATURE_GROUPS,
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "preprocessor": final_preprocessor,
        "model": final_model,
        "threshold": final_threshold,
        "threshold_selection": threshold_selection,
        "feature_importance": feature_importance,
        "selected_params": {"n_estimators": final_n_estimators},
        "selected_threshold": final_threshold,
        "extractor_config": load_extractor_config(training_config),
        "training_config": training_config,
    }
    metrics = {
        "model_name": "xgb",
        "dropped_feature_groups": effective_drop_feature_groups,
        "dropped_feature_columns": effective_drop_feature_columns,
        "selected_params": {"n_estimators": final_n_estimators},
        "selected_threshold": final_threshold,
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "feature_columns": feature_columns,
    }
    return artifact, metrics


def train_xgb_from_config(
    config: str | Path | dict[str, Any],
    *,
    persist: bool = True,
    drop_feature_groups: list[str] | None = None,
    drop_feature_columns: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    training_config = load_training_config(config)
    features, labels, splits = load_training_tables(training_config)
    artifact, metrics = train_xgb_model(
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
