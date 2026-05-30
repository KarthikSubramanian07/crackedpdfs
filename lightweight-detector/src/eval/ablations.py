from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.common import load_yaml_config, resolve_path
from src.eval.plots import save_ablation_plot
from src.features.schema import FEATURE_GROUPS
from src.models.train_logreg import train_logreg_model
from src.models.train_hybrid import train_hybrid_model
from src.models.train_text import train_text_tfidf_model
from src.models.train_xgb import train_xgb_model


def run_ablations(
    *,
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: dict[str, Any],
    model_entries: list[dict[str, Any]],
    output_dir: str | Path,
    settings: dict[str, Any] | None = None,
) -> dict[str, str]:
    ablation_settings = settings or {}
    include_group_ablations = bool(ablation_settings.get("include_group_ablations", True))
    custom_specs = ablation_settings.get("custom_specs", []) or []

    rows: list[dict[str, Any]] = []
    for model_entry in model_entries:
        training_config = load_yaml_config(model_entry["training_config"])
        model_name = str(training_config.get("model_name"))
        trainer = _select_trainer(model_name)

        _, baseline_metrics = _train_for_ablation(trainer, features, labels, splits, training_config)
        rows.append(
            _metric_row(
                model_name,
                ablation_name="baseline",
                metrics=baseline_metrics,
                drop_feature_groups=[],
                drop_feature_columns=[],
            )
        )

        if model_name == "text_tfidf":
            continue

        if include_group_ablations:
            for group_name in FEATURE_GROUPS:
                _, ablation_metrics = _train_for_ablation(
                    trainer,
                    features,
                    labels,
                    splits,
                    training_config,
                    drop_feature_groups=[group_name],
                )
                rows.append(
                    _metric_row(
                        model_name,
                        ablation_name=f"drop_group:{group_name}",
                        metrics=ablation_metrics,
                        drop_feature_groups=[group_name],
                        drop_feature_columns=[],
                    )
                )

        for spec in custom_specs:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "custom")
            drop_groups = [str(value) for value in spec.get("drop_feature_groups", []) or []]
            drop_columns = [str(value) for value in spec.get("drop_feature_columns", []) or []]
            _, ablation_metrics = _train_for_ablation(
                trainer,
                features,
                labels,
                splits,
                training_config,
                drop_feature_groups=drop_groups,
                drop_feature_columns=drop_columns,
            )
            rows.append(
                _metric_row(
                    model_name,
                    ablation_name=name,
                    metrics=ablation_metrics,
                    drop_feature_groups=drop_groups,
                    drop_feature_columns=drop_columns,
                )
            )

    ablation_df = pd.DataFrame.from_records(rows)
    metrics_path = resolve_path(Path(output_dir) / "metrics" / "ablations.csv")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    ablation_df.to_csv(metrics_path, index=False)

    plot_path = resolve_path(Path(output_dir) / "plots" / "ablations_f1.png")
    save_ablation_plot(ablation_df, output_path=plot_path, title="Feature Group Ablations")
    return {
        "ablation_csv": str(metrics_path),
        "ablation_plot": str(plot_path),
    }


def _select_trainer(model_name: str):
    if model_name == "logreg":
        return train_logreg_model
    if model_name == "xgb":
        return train_xgb_model
    if model_name == "text_tfidf":
        return train_text_tfidf_model
    if model_name == "hybrid":
        return train_hybrid_model
    raise ValueError(f"Unsupported model for ablation: {model_name}")


def _train_for_ablation(trainer: Any, features: pd.DataFrame, labels: pd.DataFrame, splits: dict[str, Any], training_config: dict[str, Any], **kwargs: Any):
    if str(training_config.get("model_name")) in {"text_tfidf", "hybrid"}:
        from src.data.load_metadata import load_dataset_config

        dataset_config = load_dataset_config(training_config["dataset_config"])
        if str(training_config.get("model_name")) == "text_tfidf":
            return trainer(labels, splits, training_config, dataset_config)
        return trainer(features, labels, splits, training_config, dataset_config, **kwargs)
    return trainer(features, labels, splits, training_config, **kwargs)


def _metric_row(
    model_name: str,
    *,
    ablation_name: str,
    metrics: dict[str, Any],
    drop_feature_groups: list[str],
    drop_feature_columns: list[str],
) -> dict[str, Any]:
    test_metrics = metrics["test_metrics"]
    return {
        "model_name": model_name,
        "ablation_name": ablation_name,
        "removed_group": ablation_name,
        "dropped_groups": ",".join(drop_feature_groups),
        "dropped_columns": ",".join(drop_feature_columns),
        "dropped_column_count": len(drop_feature_columns),
        "f1": test_metrics["f1"],
        "precision": test_metrics["precision"],
        "recall": test_metrics["recall"],
        "roc_auc": test_metrics["roc_auc"],
        "pr_auc": test_metrics["pr_auc"],
    }
