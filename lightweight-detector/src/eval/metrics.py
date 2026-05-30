from __future__ import annotations

from typing import Any

import numpy as np


def select_best_threshold(
    y_true: np.ndarray | list[int],
    y_score: np.ndarray | list[float],
    *,
    metric: str = "f1",
) -> dict[str, Any]:
    y_true_arr = np.asarray(y_true, dtype=int)
    y_score_arr = np.asarray(y_score, dtype=float)
    candidates = sorted({0.5, *[float(value) for value in y_score_arr.tolist()]})
    if not candidates:
        return {"threshold": 0.5, "metric": metric, "score": 0.0}

    best_threshold = 0.5
    best_score = float("-inf")
    for threshold in candidates:
        metrics = compute_classification_metrics(y_true_arr, y_score_arr, threshold=threshold)
        score = metrics.get(metric)
        if score is None:
            continue
        score_float = float(score)
        if score_float > best_score:
            best_score = score_float
            best_threshold = float(threshold)

    if best_score == float("-inf"):
        best_score = 0.0
    return {"threshold": best_threshold, "metric": metric, "score": float(best_score)}


def compute_classification_metrics(
    y_true: np.ndarray | list[int],
    y_score: np.ndarray | list[float],
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        balanced_accuracy_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        precision_recall_curve,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )

    y_true_arr = np.asarray(y_true, dtype=int)
    y_score_arr = np.asarray(y_score, dtype=float)
    y_pred = (y_score_arr >= threshold).astype(int)

    cm = confusion_matrix(y_true_arr, y_pred, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in cm.ravel()]
    specificity = tn / (tn + fp) if (tn + fp) else 0.0

    metrics: dict[str, Any] = {
        "threshold": float(threshold),
        "support": int(len(y_true_arr)),
        "positives": int(y_true_arr.sum()),
        "negatives": int(len(y_true_arr) - y_true_arr.sum()),
        "accuracy": float(accuracy_score(y_true_arr, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true_arr, y_pred)),
        "precision": float(precision_score(y_true_arr, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true_arr, y_pred, zero_division=0)),
        "specificity": float(specificity),
        "false_positive_rate": float(1.0 - specificity),
        "false_negative_rate": float(1.0 - recall_score(y_true_arr, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true_arr, y_pred, zero_division=0)),
        "brier_score": float(brier_score_loss(y_true_arr, y_score_arr)),
        "confusion_matrix": cm.tolist(),
    }

    if len(np.unique(y_true_arr)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true_arr, y_score_arr))
        metrics["pr_auc"] = float(average_precision_score(y_true_arr, y_score_arr))

        fpr, tpr, _ = roc_curve(y_true_arr, y_score_arr)
        precision, recall, _ = precision_recall_curve(y_true_arr, y_score_arr)
        prob_true, prob_pred = calibration_curve(
            y_true_arr, y_score_arr, n_bins=min(10, max(2, len(y_true_arr))), strategy="quantile"
        )

        metrics["roc_curve"] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
        metrics["pr_curve"] = {"precision": precision.tolist(), "recall": recall.tolist()}
        metrics["calibration_curve"] = {
            "prob_true": prob_true.tolist(),
            "prob_pred": prob_pred.tolist(),
        }
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
        metrics["roc_curve"] = None
        metrics["pr_curve"] = None
        metrics["calibration_curve"] = None

    return metrics
