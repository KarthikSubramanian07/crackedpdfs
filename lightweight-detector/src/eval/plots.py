from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.common import resolve_path


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    return plt


def save_confusion_matrix(confusion: list[list[int]], output_path: str | Path, title: str) -> str:
    plt = _plt()
    path = resolve_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(4, 4))
    axis.imshow(confusion, cmap="Blues")
    axis.set_title(title)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_xticks([0, 1], labels=["benign", "injected"])
    axis.set_yticks([0, 1], labels=["benign", "injected"])
    for i in range(2):
        for j in range(2):
            axis.text(j, i, str(confusion[i][j]), ha="center", va="center", color="black")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return str(path)


def save_curve_plot(
    x: list[float],
    y: list[float],
    *,
    output_path: str | Path,
    title: str,
    xlabel: str,
    ylabel: str,
    diagonal: bool = False,
) -> str:
    plt = _plt()
    path = resolve_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(5, 4))
    axis.plot(x, y, linewidth=2.0)
    if diagonal:
        axis.plot([0, 1], [0, 1], linestyle="--", linewidth=1.0, color="gray")
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return str(path)


def save_calibration_plot(
    prob_pred: list[float],
    prob_true: list[float],
    *,
    output_path: str | Path,
    title: str,
) -> str:
    plt = _plt()
    path = resolve_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(5, 4))
    axis.plot(prob_pred, prob_true, marker="o", linewidth=2.0)
    axis.plot([0, 1], [0, 1], linestyle="--", linewidth=1.0, color="gray")
    axis.set_title(title)
    axis.set_xlabel("Predicted probability")
    axis.set_ylabel("Observed frequency")
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return str(path)


def save_feature_importance_plot(
    feature_importance: dict[str, float],
    *,
    output_path: str | Path,
    title: str,
    top_k: int = 15,
) -> str:
    plt = _plt()
    path = resolve_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    items = sorted(feature_importance.items(), key=lambda item: item[1], reverse=True)[:top_k]
    labels = [name for name, _ in items]
    values = [value for _, value in items]

    figure, axis = plt.subplots(figsize=(8, max(4, len(items) * 0.35)))
    axis.barh(labels[::-1], values[::-1])
    axis.set_title(title)
    axis.set_xlabel("Importance")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return str(path)


def save_ablation_plot(frame: pd.DataFrame, *, output_path: str | Path, title: str) -> str:
    plt = _plt()
    path = resolve_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    label_column = "ablation_name" if "ablation_name" in frame.columns else "removed_group"
    figure, axis = plt.subplots(figsize=(8, 4))
    for model_name, group in frame.groupby("model_name"):
        axis.plot(group[label_column], group["f1"], marker="o", linewidth=2.0, label=model_name)
    axis.set_title(title)
    axis.set_xlabel("Ablation")
    axis.set_ylabel("Test F1")
    axis.grid(alpha=0.25)
    axis.legend()
    axis.tick_params(axis="x", labelrotation=30)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return str(path)
