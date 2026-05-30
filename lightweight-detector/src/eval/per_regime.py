from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from src.eval.metrics import compute_classification_metrics


def compute_per_regime_metrics(
    metadata: pd.DataFrame,
    y_true: np.ndarray,
    y_score: np.ndarray,
    regime_columns: Iterable[str],
    *,
    threshold: float = 0.5,
) -> pd.DataFrame:
    aligned = metadata.reset_index(drop=True).copy()
    aligned["y_true"] = y_true
    aligned["y_score"] = y_score

    rows: list[dict[str, object]] = []
    for column in regime_columns:
        if column not in aligned.columns:
            continue
        for value, group in aligned.groupby(column, dropna=False):
            metrics = compute_classification_metrics(
                group["y_true"].to_numpy(),
                group["y_score"].to_numpy(),
                threshold=threshold,
            )
            rows.append(
                {
                    "regime_column": column,
                    "regime_value": "null" if pd.isna(value) else str(value),
                    "support": int(len(group)),
                    "positive_rate": float(group["y_true"].mean()),
                    "accuracy": metrics["accuracy"],
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "f1": metrics["f1"],
                    "roc_auc": metrics["roc_auc"],
                    "pr_auc": metrics["pr_auc"],
                    "brier_score": metrics["brier_score"],
                }
            )

    return pd.DataFrame.from_records(rows)
