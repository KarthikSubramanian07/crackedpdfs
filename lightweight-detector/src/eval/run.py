from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.common import load_yaml_config, resolve_path, write_json
from src.data.load_metadata import load_dataset_config
from src.data.build_splits import load_splits
from src.eval.ablations import run_ablations
from src.eval.baselines import extract_pdf_text, run_promptguard_baseline, run_rule_baseline
from src.eval.metrics import compute_classification_metrics
from src.eval.per_regime import compute_per_regime_metrics
from src.eval.plots import (
    save_calibration_plot,
    save_confusion_matrix,
    save_curve_plot,
    save_feature_importance_plot,
)
from src.features.schema import FEATURE_COLUMNS, FORBIDDEN_FEATURE_COLUMNS
from src.models.inference import load_model_artifact, predict_scores
from src.models.text_preprocessing import (
    DEFAULT_BENCHMARK_WRAPPERS,
    DEFAULT_SYNTHETIC_PHRASE_MARKERS,
    apply_text_preprocessing,
    audit_text_feature_weights,
)
from src.models.train_text import train_text_tfidf_model
from src.models.train_hybrid import train_hybrid_model
from src.models.train_logreg import train_logreg_model
from src.models.train_xgb import train_xgb_model


def evaluate_from_config(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    config_path = None if isinstance(config, dict) else resolve_path(config)
    eval_config = load_yaml_config(config) if not isinstance(config, dict) else config
    dataset_config = load_dataset_config(eval_config["dataset_config"])
    features = pd.read_parquet(resolve_path(eval_config["features_path"]))
    labels = pd.read_parquet(resolve_path(eval_config["labels_path"]))
    splits = load_splits(resolve_path(eval_config["splits_path"]))
    merged = labels.merge(features, on="pdf_id", how="inner", validate="one_to_one")
    test_frame = merged[merged["pdf_id"].isin(splits["test_ids"])].copy().reset_index(drop=True)
    if test_frame.empty:
        raise ValueError("Test split is empty; cannot evaluate.")

    artifacts_dir = resolve_path(eval_config["artifacts_dir"])
    metrics_dir = artifacts_dir / "metrics"
    plots_dir = artifacts_dir / "plots"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {"models": {}, "baselines": {}}
    summary["split_strategy"] = splits.get("split_strategy", "random_grouped")
    summary["holdout"] = splits.get("holdout")
    y_true = test_frame["label"].astype(int).to_numpy()
    bootstrap_config = eval_config.get("bootstrap", {}) or {}
    bootstrap_iterations = int(bootstrap_config.get("iterations", 0) or 0)
    bootstrap_seed = int(bootstrap_config.get("random_state", 42) or 42)
    leakage_gate_config = eval_config.get("leakage_gate", {}) or {}
    single_feature_threshold = float(
        leakage_gate_config.get(
            "single_feature_accuracy_threshold",
            (eval_config.get("claim_thresholds") or {}).get("single_feature_accuracy_threshold", 0.95),
        )
    )
    shortcut_audit_path = _write_shortcut_audit(
        test_frame,
        y_true,
        metrics_dir / "shortcut_feature_audit.csv",
    )
    summary["shortcut_feature_audit_path"] = str(shortcut_audit_path)
    summary["leakage_gate"] = {
        "single_feature_accuracy_threshold": single_feature_threshold,
        "fail_on_shortcut_risk": bool(leakage_gate_config.get("fail_on_shortcut_risk", False)),
    }
    summary["shortcut_feature_risks"] = _shortcut_feature_risks(
        shortcut_audit_path,
        threshold=single_feature_threshold,
    )

    for model_entry in eval_config.get("model_artifacts", []):
        model_name = model_entry["name"]
        artifact = load_model_artifact(model_entry["path"])
        scores = predict_scores(artifact, test_frame)
        threshold = float(artifact.get("threshold", 0.5))
        metrics = compute_classification_metrics(y_true, scores, threshold=threshold)
        text_audit = _text_detector_audit(
            artifact,
            test_frame,
            y_true,
            threshold=threshold,
            baseline_metrics=metrics,
            eval_config=eval_config,
        )

        metrics_path = metrics_dir / f"{model_name}_eval_metrics.json"
        write_json(metrics, metrics_path)

        artifact_paths = _write_eval_artifacts(
            test_frame,
            np.asarray(y_true, dtype=int),
            np.asarray(scores, dtype=float),
            eval_config=eval_config,
            metrics_dir=metrics_dir,
            name=model_name,
            threshold=threshold,
        )

        plot_paths = {
            "confusion_matrix": save_confusion_matrix(
                metrics["confusion_matrix"],
                plots_dir / f"{model_name}_confusion_matrix.png",
                f"{model_name} confusion matrix",
            ),
            "feature_importance": save_feature_importance_plot(
                artifact.get("feature_importance", {}),
                output_path=plots_dir / f"{model_name}_feature_importance.png",
                title=f"{model_name} feature importance",
            ),
        }

        if metrics.get("roc_curve"):
            plot_paths["roc_curve"] = save_curve_plot(
                metrics["roc_curve"]["fpr"],
                metrics["roc_curve"]["tpr"],
                output_path=plots_dir / f"{model_name}_roc.png",
                title=f"{model_name} ROC",
                xlabel="False positive rate",
                ylabel="True positive rate",
                diagonal=True,
            )
        if metrics.get("pr_curve"):
            plot_paths["pr_curve"] = save_curve_plot(
                metrics["pr_curve"]["recall"],
                metrics["pr_curve"]["precision"],
                output_path=plots_dir / f"{model_name}_pr.png",
                title=f"{model_name} Precision-Recall",
                xlabel="Recall",
                ylabel="Precision",
            )
        if metrics.get("calibration_curve"):
            plot_paths["calibration"] = save_calibration_plot(
                metrics["calibration_curve"]["prob_pred"],
                metrics["calibration_curve"]["prob_true"],
                output_path=plots_dir / f"{model_name}_calibration.png",
                title=f"{model_name} calibration",
            )

        summary["models"][model_name] = {
            "metrics_path": str(metrics_path),
            **artifact_paths,
            "plots": plot_paths,
            "metrics": metrics,
            "balanced_evaluation": _compute_balanced_evaluation(test_frame, y_true, scores, threshold),
            "confidence_intervals": _bootstrap_metric_intervals(
                y_true,
                scores,
                threshold=threshold,
                iterations=bootstrap_iterations,
                random_state=bootstrap_seed,
            ),
            "paired_contrast": _compute_paired_contrast_metrics(test_frame, scores),
            "risk_flags": _leakage_risk_flags(artifact),
            **text_audit,
        }
        if eval_config.get("run_sanity_checks", False):
            training_config = load_yaml_config(model_entry["training_config"])
            summary["models"][model_name]["sanity_checks"] = {
                "label_shuffle": _run_label_shuffle_sanity(
                    features,
                    labels,
                    splits,
                    training_config,
                )
            }

    for baseline_entry in eval_config.get("baselines", []):
        baseline_name = str(baseline_entry.get("name", "")).strip()
        if not baseline_name or baseline_entry.get("enabled", True) is False:
            continue

        threshold = float(baseline_entry.get("threshold", 0.5))
        if baseline_name == "rule":
            scores = run_rule_baseline(test_frame)
        elif baseline_name == "promptguard":
            scores = _resolve_promptguard_scores(
                test_frame,
                dataset_config=dataset_config,
                baseline_entry=baseline_entry,
                metrics_dir=metrics_dir,
            )
        else:
            raise ValueError(f"Unsupported baseline: {baseline_name}")

        metrics = compute_classification_metrics(y_true, scores, threshold=threshold)
        metrics_path = metrics_dir / f"{baseline_name}_eval_metrics.json"
        write_json(metrics, metrics_path)
        artifact_paths = _write_eval_artifacts(
            test_frame,
            np.asarray(y_true, dtype=int),
            np.asarray(scores, dtype=float),
            eval_config=eval_config,
            metrics_dir=metrics_dir,
            name=baseline_name,
            threshold=threshold,
        )
        summary["baselines"][baseline_name] = {
            "metrics_path": str(metrics_path),
            **artifact_paths,
            "metrics": metrics,
            "balanced_evaluation": _compute_balanced_evaluation(test_frame, y_true, scores, threshold),
            "confidence_intervals": _bootstrap_metric_intervals(
                y_true,
                scores,
                threshold=threshold,
                iterations=bootstrap_iterations,
                random_state=bootstrap_seed,
            ),
            "paired_contrast": _compute_paired_contrast_metrics(test_frame, scores),
        }

    if eval_config.get("run_ablations", False):
        summary["ablations"] = run_ablations(
            features=features,
            labels=labels,
            splits=splits,
            model_entries=eval_config.get("model_artifacts", []),
            output_dir=artifacts_dir,
            settings=eval_config.get("ablations"),
        )

    hard_setting_path = metrics_dir / "hard_setting_summary.csv"
    hard_setting_df = _build_hard_setting_summary(summary)
    hard_setting_df.to_csv(hard_setting_path, index=False)

    summary["hard_setting_summary_path"] = str(hard_setting_path)
    summary["reproducibility_bundle"] = _write_reproducibility_bundle(
        eval_config=eval_config,
        eval_config_path=config_path,
        artifacts_dir=artifacts_dir,
    )
    summary["claim_readiness"] = _build_claim_readiness(summary, eval_config)
    summary_path = metrics_dir / "metrics.json"
    write_json(summary, summary_path)
    if bool((eval_config.get("claim_thresholds") or {}).get("fail_on_blocked", False)):
        readiness = summary["claim_readiness"]
        if readiness.get("status") == "blocked_for_strong_claims":
            raise RuntimeError(
                "Claim readiness gate failed: " + "; ".join(readiness.get("blockers", []))
            )
    if summary["shortcut_feature_risks"] and summary["leakage_gate"]["fail_on_shortcut_risk"]:
        risky = ", ".join(str(item.get("feature")) for item in summary["shortcut_feature_risks"][:10])
        raise RuntimeError(
            "Leakage gate failed: trainable single-feature shortcut risk above "
            f"{single_feature_threshold:.3f}: {risky}"
        )
    summary["summary_path"] = str(summary_path)
    return summary


def _write_eval_artifacts(
    frame: pd.DataFrame,
    y_true: np.ndarray,
    scores: np.ndarray,
    *,
    eval_config: dict[str, Any],
    metrics_dir: Path,
    name: str,
    threshold: float,
) -> dict[str, str]:
    regime_columns = list(eval_config.get("regime_columns", []))
    per_regime_df = compute_per_regime_metrics(
        frame,
        y_true,
        scores,
        regime_columns,
        threshold=threshold,
    )
    per_regime_path = metrics_dir / f"{name}_per_regime.csv"
    per_regime_df.to_csv(per_regime_path, index=False)

    injected_only_mask = frame["label"].astype(int) == 1
    injected_only_frame = frame.loc[injected_only_mask].reset_index(drop=True)
    injected_only_true = np.asarray(y_true[injected_only_mask.to_numpy()], dtype=int)
    injected_only_scores = np.asarray(scores[injected_only_mask.to_numpy()], dtype=float)

    per_message_type = compute_per_regime_metrics(
        injected_only_frame,
        injected_only_true,
        injected_only_scores,
        ["message_type"],
        threshold=threshold,
    )
    if not per_message_type.empty:
        per_message_type["subgroup_scope"] = "injected_only"
    per_message_type_path = metrics_dir / f"{name}_per_message_type.csv"
    per_message_type.to_csv(per_message_type_path, index=False)

    per_attack_family = compute_per_regime_metrics(
        injected_only_frame,
        injected_only_true,
        injected_only_scores,
        ["attack_family"],
        threshold=threshold,
    )
    if not per_attack_family.empty:
        per_attack_family["subgroup_scope"] = "injected_only"
    per_attack_family_path = metrics_dir / f"{name}_per_attack_family.csv"
    per_attack_family.to_csv(per_attack_family_path, index=False)

    benign_confounder_mask = (
        (frame["label"].astype(int) == 0) &
        (frame.get("benign_confounder_family", pd.Series("none", index=frame.index)).astype(str) != "none")
    )
    benign_confounder_frame = frame.loc[benign_confounder_mask].reset_index(drop=True)
    benign_confounder_true = np.asarray(y_true[benign_confounder_mask.to_numpy()], dtype=int)
    benign_confounder_scores = np.asarray(scores[benign_confounder_mask.to_numpy()], dtype=float)
    per_benign_confounder = compute_per_regime_metrics(
        benign_confounder_frame,
        benign_confounder_true,
        benign_confounder_scores,
        ["benign_confounder_family"],
        threshold=threshold,
    )
    if not per_benign_confounder.empty:
        per_benign_confounder["subgroup_scope"] = "benign_confounders_only"
        per_benign_confounder["false_positive_rate"] = 1.0 - per_benign_confounder["accuracy"].astype(float)
    per_benign_confounder_path = metrics_dir / f"{name}_per_benign_confounder_family.csv"
    per_benign_confounder.to_csv(per_benign_confounder_path, index=False)

    misclassified_path = _save_misclassifications(
        frame,
        scores,
        threshold=threshold,
        output_path=metrics_dir / f"{name}_misclassifications.csv",
    )
    return {
        "per_regime_path": str(per_regime_path),
        "per_message_type_path": str(per_message_type_path),
        "per_attack_family_path": str(per_attack_family_path),
        "per_benign_confounder_family_path": str(per_benign_confounder_path),
        "misclassifications_path": str(misclassified_path),
    }


def _save_misclassifications(
    frame: pd.DataFrame,
    scores: np.ndarray,
    *,
    threshold: float,
    output_path: Path,
) -> Path:
    predicted = (scores >= threshold).astype(int)
    error_mask = predicted != frame["label"].astype(int).to_numpy()
    columns = [
        "pdf_id",
        "base_pdf_id",
        "label",
        "source_type",
        "spatial_regime",
        "rendering_regime",
        "structural_regime",
        "message_type",
        "attack_family",
        "message_variant_id",
    ]
    available_columns = [column for column in columns if column in frame.columns]
    misclassified = frame.loc[error_mask, available_columns].copy()
    misclassified["prediction"] = predicted[error_mask]
    misclassified["risk_score"] = scores[error_mask]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    misclassified.to_csv(output_path, index=False)
    return output_path


def _write_shortcut_audit(
    frame: pd.DataFrame,
    y_true: np.ndarray,
    output_path: Path,
) -> Path:
    rows: list[dict[str, Any]] = []
    trainable_features = set(FEATURE_COLUMNS)
    for column in frame.columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.isna().all():
            continue
        values = series.fillna(0.0).to_numpy(dtype=float)
        positive_mask = values > 0.0
        negative_mask = values <= 0.0
        for direction, prediction in [
            ("gt_zero_means_injected", positive_mask.astype(int)),
            ("lte_zero_means_injected", negative_mask.astype(int)),
        ]:
            accuracy = float(np.mean(prediction == y_true)) if len(y_true) else 0.0
            rows.append(
                {
                    "feature": column,
                    "feature_scope": _feature_scope(column, trainable_features),
                    "rule": direction,
                    "accuracy": accuracy,
                    "predicted_positive": int(prediction.sum()),
                    "support": int(len(y_true)),
                    "benign_min": float(np.min(values[y_true == 0])) if np.any(y_true == 0) else None,
                    "benign_max": float(np.max(values[y_true == 0])) if np.any(y_true == 0) else None,
                    "injected_min": float(np.min(values[y_true == 1])) if np.any(y_true == 1) else None,
                    "injected_max": float(np.max(values[y_true == 1])) if np.any(y_true == 1) else None,
                }
            )

    audit = pd.DataFrame.from_records(rows)
    if not audit.empty:
        audit = audit.sort_values(["accuracy", "feature", "rule"], ascending=[False, True, True])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_path, index=False)
    return output_path


def _feature_scope(column: str, trainable_features: set[str]) -> str:
    if column in trainable_features:
        return "trainable_feature"
    if column in FORBIDDEN_FEATURE_COLUMNS:
        return "forbidden_metadata"
    return "metadata_or_auxiliary"


def _shortcut_feature_risks(audit_path: Path, threshold: float = 0.95) -> list[dict[str, Any]]:
    audit = pd.read_csv(audit_path)
    if audit.empty or "feature_scope" not in audit.columns:
        return []
    risky = audit[
        (audit["feature_scope"] == "trainable_feature") &
        (audit["accuracy"].astype(float) >= threshold)
    ].copy()
    if risky.empty:
        return []
    risky = risky.sort_values(["accuracy", "feature"], ascending=[False, True])
    return [
        {
            "feature": str(row.feature),
            "rule": str(row.rule),
            "accuracy": float(row.accuracy),
            "threshold": float(threshold),
        }
        for row in risky.head(25).itertuples(index=False)
    ]


def _compute_paired_contrast_metrics(frame: pd.DataFrame, scores: np.ndarray) -> dict[str, Any]:
    group_column = "triad_id" if "triad_id" in frame.columns else "pair_id" if "pair_id" in frame.columns else "base_pdf_id"
    columns = ["pdf_id", group_column, "label", "benign_confounder_family"]
    if "pdf_role" in frame.columns:
        columns.append("pdf_role")
    scored = frame[columns].copy()
    scored["score"] = np.asarray(scores, dtype=float)
    rows: list[dict[str, Any]] = []

    for group_id, group in scored.groupby(group_column, sort=False):
        injected_mask = group["label"].astype(int) == 1
        if "pdf_role" in group.columns:
            injected_mask = injected_mask & (group["pdf_role"].astype(str) == "injected_attack")
        injected_scores = group.loc[injected_mask, "score"]
        if len(injected_scores) != 1:
            continue
        injected_score = float(injected_scores.iloc[0])

        for negative_name, negative_mask in [
            (
                "benign_original",
                group["pdf_role"].astype(str).eq("benign_original")
                if "pdf_role" in group.columns
                else group["pdf_id"].astype(str).str.endswith(".benign"),
            ),
            (
                "benign_confounder",
                group["pdf_role"].astype(str).eq("benign_confounder")
                if "pdf_role" in group.columns
                else (
                    (group["label"].astype(int) == 0)
                    & (group["benign_confounder_family"].astype(str) != "none")
                ),
            ),
        ]:
            negative_scores = group.loc[negative_mask, "score"]
            if len(negative_scores) != 1:
                continue
            negative_score = float(negative_scores.iloc[0])
            rows.append(
                {
                    "pair_group_column": group_column,
                    "pair_group_id": str(group_id),
                    "negative_type": negative_name,
                    "injected_score": injected_score,
                    "negative_score": negative_score,
                    "margin": injected_score - negative_score,
                    "paired_correct": injected_score > negative_score,
                }
            )

    if not rows:
        return {
            "pair_count": 0,
            "overall_pair_accuracy": None,
            "pair_group_column": group_column,
            "by_negative_type": {},
        }

    pairs = pd.DataFrame.from_records(rows)
    by_negative_type: dict[str, Any] = {}
    for negative_type, group in pairs.groupby("negative_type", sort=True):
        correct = group["paired_correct"].astype(bool).to_numpy()
        by_negative_type[str(negative_type)] = {
            "pair_count": int(len(group)),
            "pair_accuracy": float(correct.mean()),
            "pair_accuracy_ci95": _binomial_ci95(int(correct.sum()), int(len(correct))),
            "mean_margin": float(group["margin"].mean()),
            "median_margin": float(group["margin"].median()),
        }

    overall_correct = pairs["paired_correct"].astype(bool).to_numpy()
    return {
        "pair_count": int(len(pairs)),
        "overall_pair_accuracy": float(overall_correct.mean()),
        "overall_pair_accuracy_ci95": _binomial_ci95(int(overall_correct.sum()), int(len(overall_correct))),
        "pair_group_column": group_column,
        "mean_margin": float(pairs["margin"].mean()),
        "median_margin": float(pairs["margin"].median()),
        "by_negative_type": by_negative_type,
    }


def _binomial_ci95(successes: int, n: int) -> dict[str, float | int]:
    if n <= 0:
        return {"successes": int(successes), "n": int(n), "low": 0.0, "high": 0.0}
    z = 1.959963984540054
    phat = successes / n
    denom = 1.0 + (z * z / n)
    center = (phat + (z * z / (2.0 * n))) / denom
    half_width = (z / denom) * np.sqrt((phat * (1.0 - phat) / n) + (z * z / (4.0 * n * n)))
    return {
        "successes": int(successes),
        "n": int(n),
        "low": float(max(0.0, center - half_width)),
        "high": float(min(1.0, center + half_width)),
    }


def _resolve_promptguard_scores(
    test_frame: pd.DataFrame,
    *,
    dataset_config: dict[str, Any],
    baseline_entry: dict[str, Any],
    metrics_dir: Path,
) -> np.ndarray:
    score_path = resolve_path(
        baseline_entry.get("scores_path") or metrics_dir / "promptguard_scores.csv"
    )
    reuse_scores = bool(baseline_entry.get("reuse_scores", True))
    write_scores = bool(baseline_entry.get("write_scores", True))
    model_name = str(baseline_entry.get("model_name", "meta-llama/Prompt-Guard-86M"))
    max_length = int(baseline_entry.get("max_length", 512))
    batch_size = int(baseline_entry.get("batch_size", 32))
    allow_legacy_cache = bool(baseline_entry.get("allow_legacy_cache", False))
    score_strategy = str(baseline_entry.get("score_strategy", "sum_injection_and_jailbreak"))
    extracted_texts = [
        extract_pdf_text(file_path, dataset_config)
        for file_path in test_frame["file_path"].astype(str).tolist()
    ]
    text_hashes = [_sha256_text(text) for text in extracted_texts]
    cache_metadata = pd.DataFrame(
        {
            "pdf_id": test_frame["pdf_id"].astype(str).to_numpy(),
            "model_name": model_name,
            "max_length": max_length,
            "score_strategy": score_strategy,
            "extracted_text_sha256": text_hashes,
        }
    )

    if reuse_scores and score_path.exists():
        cached = pd.read_csv(score_path)
        required = {"pdf_id", "score"}
        if not required.issubset(cached.columns):
            raise ValueError(f"PromptGuard score cache missing columns {sorted(required)}: {score_path}")
        provenance_columns = {"model_name", "max_length", "score_strategy", "extracted_text_sha256"}
        if not provenance_columns.issubset(cached.columns):
            if not allow_legacy_cache:
                missing_columns = sorted(provenance_columns - set(cached.columns))
                raise ValueError(
                    "PromptGuard score cache is missing provenance columns "
                    f"{missing_columns}: {score_path}. Recompute with reuse_scores=false "
                    "or set allow_legacy_cache=true for an explicitly non-publication run."
                )
            merged = test_frame[["pdf_id"]].merge(cached[["pdf_id", "score"]], on="pdf_id", how="left", validate="one_to_one")
        else:
            merged = cache_metadata.merge(
                cached[["pdf_id", "score", "model_name", "max_length", "score_strategy", "extracted_text_sha256"]],
                on="pdf_id",
                how="left",
                validate="one_to_one",
                suffixes=("", "_cached"),
            )
            stale_mask = (
                merged["score"].notna()
                & (
                    (merged["model_name"] != merged["model_name_cached"])
                    | (merged["max_length"].astype(int) != merged["max_length_cached"].astype(int))
                    | (merged["score_strategy"] != merged["score_strategy_cached"])
                    | (merged["extracted_text_sha256"] != merged["extracted_text_sha256_cached"])
                )
            )
            if stale_mask.any():
                stale = merged.loc[stale_mask, "pdf_id"].head(10).tolist()
                raise ValueError(
                    "PromptGuard score cache provenance does not match the current evaluation. "
                    f"Stale examples: {stale}. Recompute with reuse_scores=false."
                )
        if merged["score"].isna().any():
            missing = merged.loc[merged["score"].isna(), "pdf_id"].head(10).tolist()
            raise ValueError(
                "PromptGuard score cache does not cover the current test split. "
                f"Missing examples: {missing}. Disable reuse_scores to recompute."
            )
        return merged["score"].astype(float).to_numpy()

    scores = run_promptguard_baseline(
        test_frame,
        dataset_config=dataset_config,
        model_name=model_name,
        max_length=max_length,
        batch_size=batch_size,
        texts=extracted_texts,
    )
    if write_scores:
        score_path.parent.mkdir(parents=True, exist_ok=True)
        output = cache_metadata.copy()
        output["score"] = scores
        output["baseline_name"] = "promptguard"
        output.to_csv(score_path, index=False)
    return scores


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()


def _compute_balanced_evaluation(
    frame: pd.DataFrame,
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    rng = np.random.default_rng(42)
    positives = np.flatnonzero(np.asarray(y_true, dtype=int) == 1)
    negatives = np.flatnonzero(np.asarray(y_true, dtype=int) == 0)
    confounders = np.flatnonzero(
        (frame["label"].astype(int).to_numpy() == 0)
        & (
            frame.get("benign_confounder_family", pd.Series("none", index=frame.index))
            .astype(str)
            .to_numpy()
            != "none"
        )
    )

    return {
        "injected_vs_random_negative": _balanced_subset_metrics(
            y_true,
            scores,
            positives=positives,
            negatives=negatives,
            threshold=threshold,
            rng=rng,
        ),
        "injected_vs_benign_confounder": _balanced_subset_metrics(
            y_true,
            scores,
            positives=positives,
            negatives=confounders,
            threshold=threshold,
            rng=rng,
        ),
    }


def _balanced_subset_metrics(
    y_true: np.ndarray,
    scores: np.ndarray,
    *,
    positives: np.ndarray,
    negatives: np.ndarray,
    threshold: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    n = min(len(positives), len(negatives))
    if n <= 0:
        return {"support": 0, "positive_count": int(len(positives)), "negative_count": int(len(negatives))}
    selected_negatives = rng.choice(negatives, size=n, replace=False)
    selected = np.concatenate([positives[:n], selected_negatives])
    selected.sort()
    metrics = compute_classification_metrics(y_true[selected], scores[selected], threshold=threshold)
    return _compact_metrics(metrics)


def _bootstrap_metric_intervals(
    y_true: np.ndarray,
    scores: np.ndarray,
    *,
    threshold: float,
    iterations: int,
    random_state: int,
) -> dict[str, Any]:
    if iterations <= 0 or len(y_true) < 2:
        return {"enabled": False, "iterations": 0}
    rng = np.random.default_rng(random_state)
    metric_names = [
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "specificity",
        "f1",
        "roc_auc",
        "pr_auc",
    ]
    samples: dict[str, list[float]] = {name: [] for name in metric_names}
    y_true_arr = np.asarray(y_true, dtype=int)
    score_arr = np.asarray(scores, dtype=float)
    n = len(y_true_arr)

    attempts = 0
    max_attempts = max(iterations * 4, iterations)
    while min(len(values) for values in samples.values()) < iterations and attempts < max_attempts:
        attempts += 1
        idx = rng.integers(0, n, size=n)
        if len(np.unique(y_true_arr[idx])) < 2:
            continue
        metrics = compute_classification_metrics(y_true_arr[idx], score_arr[idx], threshold=threshold)
        for name in metric_names:
            value = metrics.get(name)
            if value is not None:
                samples[name].append(float(value))

    intervals: dict[str, Any] = {}
    for name, values in samples.items():
        if not values:
            continue
        arr = np.asarray(values, dtype=float)
        intervals[name] = {
            "mean": float(np.mean(arr)),
            "ci95_low": float(np.quantile(arr, 0.025)),
            "ci95_high": float(np.quantile(arr, 0.975)),
            "samples": int(len(arr)),
        }
    return {
        "enabled": True,
        "iterations": int(iterations),
        "successful_iterations": int(min((len(values) for values in samples.values()), default=0)),
        "random_state": int(random_state),
        "metrics": intervals,
    }


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "support",
        "positives",
        "negatives",
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "specificity",
        "false_positive_rate",
        "false_negative_rate",
        "f1",
        "roc_auc",
        "pr_auc",
        "confusion_matrix",
    ]
    return {key: metrics.get(key) for key in keys if key in metrics}


def _leakage_risk_flags(artifact: dict[str, Any]) -> list[str]:
    suspicious = {
        "num_text_outside_page_bounds",
        "frac_text_outside_page",
        "num_text_negative_coords",
        "max_abs_x",
        "max_abs_y",
        "max_distance_from_page_center",
        "mean_distance_from_page_center",
        "distance_outlier_score",
        "injection_cluster_score",
        "num_content_streams_total",
        "mean_streams_per_page",
        "avg_stream_length_bytes",
        "max_stream_length_bytes",
        "num_stream_objects",
    }
    feature_importance = artifact.get("feature_importance", {})
    ranked = [
        feature_name
        for feature_name, _ in sorted(feature_importance.items(), key=lambda item: item[1], reverse=True)[:5]
    ]
    hits = [feature_name for feature_name in ranked if feature_name in suspicious]
    if not hits:
        return []
    return [
        "Top ranked features include structurally trivial signals that deserve leakage review: "
        + ", ".join(hits)
    ]


def _build_claim_readiness(summary: dict[str, Any], eval_config: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    thresholds = eval_config.get("claim_thresholds") or {}
    primary_models = [
        str(name)
        for name in thresholds.get(
            "primary_shortcut_free_models",
            ["logreg_shortcut_free", "xgb_shortcut_free"],
        )
    ]
    min_shortcut_free_f1 = float(thresholds.get("min_shortcut_free_f1", 0.75))
    min_paired_confounder_accuracy = float(
        thresholds.get("min_paired_benign_confounder_accuracy", 0.75)
    )
    min_paired_confounder_support = int(thresholds.get("min_paired_benign_confounder_support", 30))
    min_paired_confounder_ci_low = float(thresholds.get("min_paired_benign_confounder_ci95_low", 0.60))
    max_f1_drop = float(thresholds.get("max_full_to_shortcut_free_f1_drop", 0.2))
    text_thresholds = thresholds.get("text_detector", {}) or {}
    max_wrapper_hits = int(text_thresholds.get("max_wrapper_top_weight_hits", 0))
    max_strip_f1_drop = float(text_thresholds.get("max_wrapper_strip_f1_drop", 0.05))
    max_synthetic_phrase_f1_drop = float(text_thresholds.get("max_synthetic_phrase_strip_f1_drop", 0.10))
    structural_models = [name for name in primary_models if name != "text_tfidf"]
    text_models = [name for name in primary_models if name == "text_tfidf"]
    if text_models and structural_models:
        warnings.append(
            "text_tfidf is evaluated separately from structural models; do not aggregate it with PDF-structure detector claims."
        )

    if summary.get("shortcut_feature_risks"):
        risky = ", ".join(str(item.get("feature")) for item in summary["shortcut_feature_risks"][:5])
        blockers.append(f"Trainable single-feature shortcut risk above threshold: {risky}.")

    model_metrics = {name: payload.get("metrics", {}) for name, payload in summary.get("models", {}).items()}
    perfect_models = [
        name
        for name, metrics in model_metrics.items()
        if metrics.get("accuracy") == 1.0 and metrics.get("f1") == 1.0
    ]
    if perfect_models:
        warnings.append("Perfect model scores require ablation-backed framing: " + ", ".join(perfect_models) + ".")

    for base_name in ["logreg", "xgb"]:
        full = model_metrics.get(base_name, {}).get("f1")
        shortcut_free = model_metrics.get(f"{base_name}_shortcut_free", {}).get("f1")
        if isinstance(full, (int, float)) and isinstance(shortcut_free, (int, float)):
            if float(full) - float(shortcut_free) >= max_f1_drop:
                blockers.append(
                    f"{base_name} drops from F1={float(full):.3f} to "
                    f"shortcut-free F1={float(shortcut_free):.3f}."
                )

    for model_name in primary_models:
        payload = summary.get("models", {}).get(model_name)
        if not payload:
            blockers.append(f"Primary shortcut-free model missing from evaluation: {model_name}.")
            continue
        f1 = payload.get("metrics", {}).get("f1")
        if isinstance(f1, (int, float)) and float(f1) < min_shortcut_free_f1:
            blockers.append(
                f"{model_name} shortcut-free F1={float(f1):.3f} below publication gate "
                f"{min_shortcut_free_f1:.3f}."
            )
        paired = payload.get("paired_contrast", {}).get("by_negative_type", {}).get("benign_confounder", {})
        pair_count = paired.get("pair_count")
        pair_accuracy = paired.get("pair_accuracy")
        pair_ci = paired.get("pair_accuracy_ci95") or {}
        if isinstance(pair_count, (int, float)) and int(pair_count) < min_paired_confounder_support:
            blockers.append(
                f"{model_name} paired benign-confounder support={int(pair_count)} below publication gate "
                f"{min_paired_confounder_support}."
            )
        if isinstance(pair_accuracy, (int, float)) and float(pair_accuracy) < min_paired_confounder_accuracy:
            blockers.append(
                f"{model_name} paired benign-confounder accuracy={float(pair_accuracy):.3f} "
                f"below publication gate {min_paired_confounder_accuracy:.3f}."
            )
        elif pair_accuracy is None:
            blockers.append(f"{model_name} lacks paired benign-confounder contrast metrics.")
        if isinstance(pair_ci.get("low"), (int, float)) and float(pair_ci["low"]) < min_paired_confounder_ci_low:
            blockers.append(
                f"{model_name} paired benign-confounder CI95 low={float(pair_ci['low']):.3f} "
                f"below publication gate {min_paired_confounder_ci_low:.3f}."
            )

        if model_name in {"text_tfidf", "hybrid"}:
            detector_label = model_name
            feature_audit = payload.get("feature_weight_audit") or {}
            wrapper_hit_count = int(feature_audit.get("wrapper_token_hit_count", 0) or 0)
            if wrapper_hit_count > max_wrapper_hits:
                blockers.append(
                    f"{detector_label} top-weight audit found {wrapper_hit_count} benchmark/synthetic token hits "
                    f"above gate {max_wrapper_hits}."
                )
            strip_ablation = payload.get("wrapper_token_ablation") or {}
            f1_drop = strip_ablation.get("f1_drop")
            if isinstance(f1_drop, (int, float)) and float(f1_drop) > max_strip_f1_drop:
                blockers.append(
                    f"{detector_label} F1 drops by {float(f1_drop):.3f} when known wrappers are stripped "
                    f"(gate {max_strip_f1_drop:.3f})."
                )
            elif f1_drop is None:
                blockers.append(f"{detector_label} lacks wrapper-token strip ablation metrics.")
            phrase_ablation = payload.get("synthetic_phrase_ablation") or {}
            phrase_f1_drop = phrase_ablation.get("f1_drop")
            if isinstance(phrase_f1_drop, (int, float)) and float(phrase_f1_drop) > max_synthetic_phrase_f1_drop:
                blockers.append(
                    f"{detector_label} F1 drops by {float(phrase_f1_drop):.3f} when synthetic phrase markers are stripped "
                    f"(gate {max_synthetic_phrase_f1_drop:.3f})."
                )
            elif phrase_f1_drop is None:
                blockers.append(f"{detector_label} lacks synthetic-phrase strip ablation metrics.")
            residual_audit = payload.get("residual_marker_audit") or {}
            residual_flags = residual_audit.get("flags") or []
            if residual_flags:
                examples = ", ".join(str(item.get("marker")) for item in residual_flags[:5])
                blockers.append(
                    f"{detector_label} cleaned-text residual marker audit found role-associated markers: "
                    f"{examples}."
                )

    baselines = summary.get("baselines", {})
    if "promptguard" in baselines:
        promptguard_recall = baselines["promptguard"].get("metrics", {}).get("recall")
        if isinstance(promptguard_recall, (int, float)) and float(promptguard_recall) < 0.5:
            warnings.append(f"PromptGuard recall is low ({float(promptguard_recall):.3f}); frame it as text-only baseline.")

    return {
        "status": "blocked_for_strong_claims" if blockers else "usable_with_caveats",
        "publication_gates": {
            "primary_shortcut_free_models": primary_models,
            "min_shortcut_free_f1": min_shortcut_free_f1,
            "min_paired_benign_confounder_accuracy": min_paired_confounder_accuracy,
            "min_paired_benign_confounder_support": min_paired_confounder_support,
            "min_paired_benign_confounder_ci95_low": min_paired_confounder_ci_low,
            "max_full_to_shortcut_free_f1_drop": max_f1_drop,
            "single_feature_accuracy_threshold": float(
                (eval_config.get("leakage_gate") or {}).get(
                    "single_feature_accuracy_threshold",
                    thresholds.get("single_feature_accuracy_threshold", 0.95),
                )
            ),
            "text_detector": {
                "max_wrapper_top_weight_hits": max_wrapper_hits,
                "max_wrapper_strip_f1_drop": max_strip_f1_drop,
                "max_synthetic_phrase_strip_f1_drop": max_synthetic_phrase_f1_drop,
            },
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _text_detector_audit(
    artifact: dict[str, Any],
    frame: pd.DataFrame,
    y_true: np.ndarray,
    *,
    threshold: float,
    baseline_metrics: dict[str, Any],
    eval_config: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("model_name") not in {"text_tfidf", "hybrid"}:
        return {}

    preprocessing = artifact.get("text_preprocessing", {}) or {}
    wrappers = list(preprocessing.get("known_benchmark_wrappers") or DEFAULT_BENCHMARK_WRAPPERS)
    synthetic_markers = list(
        preprocessing.get("synthetic_phrase_markers") or DEFAULT_SYNTHETIC_PHRASE_MARKERS
    )
    feature_audit = audit_text_feature_weights(
        artifact["pipeline"],
        known_wrappers=[*wrappers, *synthetic_markers],
    )

    stripped_preprocessing = {
        **preprocessing,
        "strip_known_benchmark_wrappers": True,
        "known_benchmark_wrappers": wrappers,
    }
    stripped_scores = predict_scores(
        artifact,
        frame,
        text_preprocessing_override=stripped_preprocessing,
    )
    stripped_metrics = compute_classification_metrics(y_true, stripped_scores, threshold=threshold)

    baseline_f1 = baseline_metrics.get("f1")
    wrapper_ablation = {
        "strip_known_benchmark_wrappers": True,
        "known_benchmark_wrappers": wrappers,
        "metrics": stripped_metrics,
    }
    if isinstance(baseline_f1, (int, float)):
        wrapper_ablation["f1_drop"] = float(baseline_f1) - float(stripped_metrics["f1"])

    synthetic_preprocessing = {
        **stripped_preprocessing,
        "strip_synthetic_phrase_markers": True,
        "synthetic_phrase_markers": synthetic_markers,
    }
    synthetic_scores = predict_scores(
        artifact,
        frame,
        text_preprocessing_override=synthetic_preprocessing,
    )
    synthetic_metrics = compute_classification_metrics(y_true, synthetic_scores, threshold=threshold)
    synthetic_ablation = {
        "strip_known_benchmark_wrappers": True,
        "strip_synthetic_phrase_markers": True,
        "synthetic_phrase_markers": synthetic_markers,
        "metrics": synthetic_metrics,
    }
    if isinstance(baseline_f1, (int, float)):
        synthetic_ablation["f1_drop"] = float(baseline_f1) - float(synthetic_metrics["f1"])

    return {
        "feature_weight_audit": feature_audit,
        "wrapper_token_ablation": wrapper_ablation,
        "synthetic_phrase_ablation": synthetic_ablation,
        "residual_marker_audit": _text_residual_marker_audit(
            artifact=artifact,
            frame=frame,
            wrappers=wrappers,
            synthetic_markers=synthetic_markers,
        ),
    }


def _text_residual_marker_audit(
    *,
    artifact: dict[str, Any],
    frame: pd.DataFrame,
    wrappers: list[str],
    synthetic_markers: list[str],
) -> dict[str, Any]:
    preprocessing = {
        **(artifact.get("text_preprocessing", {}) or {}),
        "strip_known_benchmark_wrappers": True,
        "known_benchmark_wrappers": wrappers,
        "strip_synthetic_phrase_markers": True,
        "synthetic_phrase_markers": synthetic_markers,
    }
    dataset_config = artifact.get("dataset_config", {}) or {}
    markers = _residual_marker_patterns([*wrappers, *synthetic_markers])
    roles = (
        frame["pdf_role"].astype(str).tolist()
        if "pdf_role" in frame.columns
        else ["unknown"] * len(frame)
    )
    role_totals: dict[str, int] = {}
    counts: dict[str, dict[str, int]] = {
        marker: {} for marker in markers
    }

    for file_path, role in zip(frame["file_path"].astype(str).tolist(), roles):
        role_totals[role] = role_totals.get(role, 0) + 1
        cleaned = apply_text_preprocessing(extract_pdf_text(file_path, dataset_config), preprocessing)
        normalized = _normalize_marker_text(cleaned)
        for marker, marker_norm in markers.items():
            if marker_norm and marker_norm in normalized:
                bucket = counts[marker]
                bucket[role] = bucket.get(role, 0) + 1

    min_count = 5
    min_role_rate = 0.05
    min_role_gap = 0.04
    flags: list[dict[str, Any]] = []
    marker_rows: list[dict[str, Any]] = []
    for marker, by_role in counts.items():
        total_hits = sum(by_role.values())
        if total_hits == 0:
            continue
        rates = {
            role: safe_count / max(role_totals.get(role, 0), 1)
            for role, safe_count in by_role.items()
        }
        max_role = max(rates, key=rates.get)
        max_rate = float(rates[max_role])
        other_rates = [rate for role, rate in rates.items() if role != max_role]
        next_rate = max(other_rates, default=0.0)
        row = {
            "marker": marker,
            "total_hits": int(total_hits),
            "role_counts": by_role,
            "role_rates": rates,
            "max_role": max_role,
            "max_role_rate": max_rate,
            "role_rate_gap": float(max_rate - next_rate),
        }
        marker_rows.append(row)
        if total_hits >= min_count and max_rate >= min_role_rate and (max_rate - next_rate) >= min_role_gap:
            flags.append(row)

    return {
        "markers_checked": sorted(markers),
        "role_totals": role_totals,
        "marker_hits": marker_rows,
        "flags": flags,
        "thresholds": {
            "min_count": min_count,
            "min_role_rate": min_role_rate,
            "min_role_gap": min_role_gap,
        },
    }


def _residual_marker_patterns(markers: list[str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for marker in markers:
        marker_text = str(marker).strip()
        normalized = _normalize_marker_text(marker_text)
        if len(normalized) >= 5:
            output[marker_text] = normalized
    for marker in ["<", ">", "</", "documentlayoutnote", "layoutcalibrationtextonly"]:
        normalized = _normalize_marker_text(marker)
        if len(normalized) >= 1:
            output[marker] = normalized
    return output


def _normalize_marker_text(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _write_reproducibility_bundle(
    *,
    eval_config: dict[str, Any],
    eval_config_path: Path | None,
    artifacts_dir: Path,
) -> dict[str, Any]:
    bundle_dir = artifacts_dir / "reproducibility"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}

    config_paths = {
        "eval_config.yaml": eval_config_path,
        "dataset_config.yaml": eval_config.get("dataset_config"),
        "splits.json": eval_config.get("splits_path"),
    }
    feature_schema_path = _infer_feature_schema_path(eval_config)
    if feature_schema_path is not None:
        config_paths["feature_schema.json"] = feature_schema_path

    for entry in eval_config.get("model_artifacts", []):
        training_config = entry.get("training_config")
        if training_config:
            safe_name = str(entry.get("name", "model")).replace("/", "_").replace("\\", "_")
            config_paths[f"model_{safe_name}_training_config.yaml"] = training_config

    for bundle_name, source in config_paths.items():
        if source is None:
            continue
        source_path = resolve_path(source)
        if not source_path.exists():
            continue
        dest = bundle_dir / bundle_name
        shutil.copy2(source_path, dest)
        copied[bundle_name] = str(dest)

    hashed_files = {
        "features": resolve_path(eval_config["features_path"]),
        "labels": resolve_path(eval_config["labels_path"]),
        "splits": resolve_path(eval_config["splits_path"]),
    }
    for bundle_name, copied_path in copied.items():
        hashed_files[f"bundle:{bundle_name}"] = Path(copied_path)

    manifest = {
        "bundle_dir": str(bundle_dir),
        "copied_files": copied,
        "file_hashes": {
            name: _file_sha256(path)
            for name, path in hashed_files.items()
            if path.exists() and path.is_file()
        },
        "exact_commands": list(
            eval_config.get("exact_commands")
            or [
                f"python -m src.cli validate-dataset --config {eval_config.get('dataset_config')}",
                f"python -m src.cli build-splits --config {eval_config.get('dataset_config')}",
                "python -m src.cli build-features --config <features_config>",
                *[
                    f"python -m src.cli train --model {_model_command_name(entry)} --config {entry.get('training_config')}"
                    for entry in eval_config.get("model_artifacts", [])
                    if entry.get("training_config")
                ],
                f"python -m src.cli evaluate --config {str(eval_config_path) if eval_config_path else '<eval_config>'}",
            ]
        ),
        "eval_artifacts_dir": str(artifacts_dir),
        "features_path": str(resolve_path(eval_config["features_path"])),
        "labels_path": str(resolve_path(eval_config["labels_path"])),
        "splits_path": str(resolve_path(eval_config["splits_path"])),
        "promptguard_cache_policy": [
            {
                "name": entry.get("name"),
                "reuse_scores": entry.get("reuse_scores"),
                "scores_path": entry.get("scores_path"),
                "allow_legacy_cache": entry.get("allow_legacy_cache", False),
                "score_strategy": entry.get("score_strategy", "sum_injection_and_jailbreak"),
            }
            for entry in eval_config.get("baselines", [])
            if str(entry.get("name", "")).strip() == "promptguard"
        ],
    }
    manifest_path = bundle_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_command_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("name", "")).lower()
    if "xgb" in name:
        return "xgb"
    if "text_tfidf" in name or name == "text":
        return "text"
    if "hybrid" in name:
        return "hybrid"
    return "logreg"


def _infer_feature_schema_path(eval_config: dict[str, Any]) -> Path | None:
    configured_path = eval_config.get("feature_schema_path")
    if configured_path:
        candidate = resolve_path(configured_path)
        if candidate.exists():
            return candidate

    artifacts_dir = resolve_path(eval_config["artifacts_dir"])
    candidates = [
        artifacts_dir / "feature_schema.json",
        artifacts_dir.parent / "feature_schema.json",
        resolve_path("data/artifacts/feature_schema.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _build_hard_setting_summary(summary: dict[str, Any]) -> pd.DataFrame:
    split_strategy = str(summary.get("split_strategy", "random_grouped"))
    setting_name = {
        "random_grouped": "in_distribution_grouped_test",
        "coverage_aware": "coverage_aware_grouped_test",
        "heldout_message_type": "heldout_message_type",
        "heldout_attack_family": "heldout_attack_family",
        "heldout_provenance": "heldout_provenance",
    }.get(split_strategy, split_strategy)
    rows: list[dict[str, Any]] = []

    for family_name, bucket in [("model", summary.get("models", {})), ("baseline", summary.get("baselines", {}))]:
        for name, payload in bucket.items():
            metrics = payload.get("metrics", {})
            rows.append(
                {
                    "entry_type": family_name,
                    "name": name,
                    "setting": setting_name,
                    "accuracy": metrics.get("accuracy"),
                    "precision": metrics.get("precision"),
                    "recall": metrics.get("recall"),
                    "f1": metrics.get("f1"),
                    "roc_auc": metrics.get("roc_auc"),
                    "pr_auc": metrics.get("pr_auc"),
                }
            )

    for name, payload in summary.get("models", {}).items():
        sanity = (payload.get("sanity_checks") or {}).get("label_shuffle") or {}
        if sanity:
            rows.append(
                {
                    "entry_type": "sanity_check",
                    "name": name,
                    "setting": "label_shuffle",
                    "accuracy": sanity.get("accuracy"),
                    "precision": sanity.get("precision"),
                    "recall": sanity.get("recall"),
                    "f1": sanity.get("f1"),
                    "roc_auc": sanity.get("roc_auc"),
                    "pr_auc": sanity.get("pr_auc"),
                }
            )

    return pd.DataFrame.from_records(rows)


def _run_label_shuffle_sanity(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: dict[str, Any],
    training_config: dict[str, Any],
) -> dict[str, Any]:
    rng = np.random.default_rng(int(training_config.get("random_state", 42)))
    shuffled = labels.copy()
    train_val_ids = set(splits.get("train_ids", [])) | set(splits.get("val_ids", []))
    mask = shuffled["pdf_id"].isin(train_val_ids)
    shuffled_labels = shuffled.loc[mask, "label"].to_numpy().copy()
    rng.shuffle(shuffled_labels)
    shuffled.loc[mask, "label"] = shuffled_labels

    model_name = str(training_config.get("model_name", ""))
    if model_name == "text_tfidf":
        dataset_config = load_dataset_config(training_config["dataset_config"])
        _, metrics = train_text_tfidf_model(shuffled, splits, training_config, dataset_config)
        test_metrics = metrics["test_metrics"]
        return {
            "accuracy": test_metrics["accuracy"],
            "precision": test_metrics["precision"],
            "recall": test_metrics["recall"],
            "f1": test_metrics["f1"],
            "roc_auc": test_metrics["roc_auc"],
            "pr_auc": test_metrics["pr_auc"],
        }
    if model_name == "hybrid":
        dataset_config = load_dataset_config(training_config["dataset_config"])
        _, metrics = train_hybrid_model(features, shuffled, splits, training_config, dataset_config)
        test_metrics = metrics["test_metrics"]
        return {
            "accuracy": test_metrics["accuracy"],
            "precision": test_metrics["precision"],
            "recall": test_metrics["recall"],
            "f1": test_metrics["f1"],
            "roc_auc": test_metrics["roc_auc"],
            "pr_auc": test_metrics["pr_auc"],
        }

    trainer = _select_trainer(model_name)
    _, metrics = trainer(features, shuffled, splits, training_config)
    test_metrics = metrics["test_metrics"]
    return {
        "accuracy": test_metrics["accuracy"],
        "precision": test_metrics["precision"],
        "recall": test_metrics["recall"],
        "f1": test_metrics["f1"],
        "roc_auc": test_metrics["roc_auc"],
        "pr_auc": test_metrics["pr_auc"],
    }


def _select_trainer(model_name: str):
    if model_name == "logreg":
        return train_logreg_model
    if model_name == "xgb":
        return train_xgb_model
    if model_name == "hybrid":
        return train_hybrid_model
    raise ValueError(f"Unsupported trainer for sanity check: {model_name}")
