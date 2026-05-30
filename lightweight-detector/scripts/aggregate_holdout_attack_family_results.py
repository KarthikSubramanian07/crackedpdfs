from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common import load_yaml_config, resolve_path
from src.data.build_splits import load_splits
from src.eval.baselines import run_rule_baseline
from src.eval.metrics import compute_classification_metrics
from src.models.inference import load_model_artifact, predict_scores


MATCHED_CONFOUNDER_FAMILY = {
    "steganographic_acrostic": "benign_acrostic_editorial_note",
    "microglyph_steganography": "benign_microglyph_registration_mark",
    "semantic_fragmentation": "benign_semantic_fragmentation_note",
    "layout_mimicry": "benign_layout_mimicry_note",
    "margin_microtext": "benign_margin_microtext",
    "in_page_low_contrast_text": "benign_low_contrast_watermark",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate held-out attack-family metrics.")
    parser.add_argument("--manifest", default="configs/holdout_attack_families/manifest.yaml")
    parser.add_argument("--output", default="data/artifacts/holdout_attack_family/aggregate_metrics.csv")
    parser.add_argument(
        "--target-output",
        default="data/artifacts/holdout_attack_family/target_family_focus_metrics.csv",
    )
    parser.add_argument(
        "--matched-output",
        default="data/artifacts/holdout_attack_family/matched_counterfactual_metrics.csv",
    )
    args = parser.parse_args()

    manifest = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    aggregate_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []

    for item in manifest["holdouts"]:
        family = str(item["attack_family"])
        eval_config = load_yaml_config(item["eval_config"])
        metrics_path = resolve_path(eval_config["artifacts_dir"]) / "metrics" / "metrics.json"
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        aggregate_eval_config = load_yaml_config(item.get("model_only_eval_config") or item["eval_config"])
        aggregate_rows.extend(_aggregate_current_artifact_rows(family, aggregate_eval_config, metrics_payload))
        focus_rows = _target_family_focus_rows(family, aggregate_eval_config, metrics_payload)
        target_rows.extend(focus_rows["target"])
        matched_rows.extend(focus_rows["matched"])

    _write_csv(Path(args.output), aggregate_rows)
    _write_csv(Path(args.target_output), target_rows)
    _write_csv(Path(args.matched_output), matched_rows)
    print(args.output)
    print(args.target_output)
    print(args.matched_output)


def _aggregate_summary_rows(family: str, metrics_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket_name in ["models", "baselines"]:
        for method, payload in metrics_payload.get(bucket_name, {}).items():
            metrics = payload.get("metrics", {})
            balanced = payload.get("balanced_evaluation", {}).get("injected_vs_benign_confounder", {})
            paired = payload.get("paired_contrast", {}).get("by_negative_type", {}).get("benign_confounder", {})
            f1_ci = payload.get("confidence_intervals", {}).get("metrics", {}).get("f1", {})
            rows.append(
                {
                    "family": family,
                    "method": method,
                    "scope": "group_holdout_all_test_rows",
                    "support": metrics.get("support"),
                    "positives": metrics.get("positives"),
                    "negatives": metrics.get("negatives"),
                    "accuracy": metrics.get("accuracy"),
                    "balanced_accuracy": metrics.get("balanced_accuracy"),
                    "precision": metrics.get("precision"),
                    "recall": metrics.get("recall"),
                    "f1": metrics.get("f1"),
                    "f1_ci95_low": f1_ci.get("ci95_low"),
                    "f1_ci95_high": f1_ci.get("ci95_high"),
                    "roc_auc": metrics.get("roc_auc"),
                    "pr_auc": metrics.get("pr_auc"),
                    "balanced_confounder_f1": balanced.get("f1"),
                    "paired_confounder_accuracy": paired.get("pair_accuracy"),
                    "claim_status": metrics_payload.get("claim_readiness", {}).get("status"),
                    "shortcut_risks": ";".join(
                        str(risk.get("feature", "")) for risk in metrics_payload.get("shortcut_feature_risks", [])
                    ),
                }
            )
    return rows


def _aggregate_current_artifact_rows(
    family: str,
    eval_config: dict[str, Any],
    metrics_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    features = pd.read_parquet(resolve_path(eval_config["features_path"]))
    labels = pd.read_parquet(resolve_path(eval_config["labels_path"]))
    splits = load_splits(resolve_path(eval_config["splits_path"]))
    merged = labels.merge(features, on="pdf_id", how="inner", validate="one_to_one")
    test_frame = merged[merged["pdf_id"].isin(splits["test_ids"])].copy().reset_index(drop=True)
    y_true = test_frame["label"].astype(int).to_numpy()

    rows: list[dict[str, Any]] = []
    for entry in eval_config.get("model_artifacts", []):
        method = str(entry["name"])
        artifact = load_model_artifact(entry["path"])
        scores = predict_scores(artifact, test_frame)
        threshold = float(artifact.get("threshold", 0.5))
        metrics = compute_classification_metrics(y_true, scores, threshold=threshold)
        rows.append(
            _aggregate_metric_row(
                family,
                method,
                metrics,
                metrics_payload,
                wrapper_audit=_wrapper_audit_status(metrics_payload, method),
            )
        )

    for baseline in eval_config.get("baselines", []):
        method = str(baseline.get("name", ""))
        if baseline.get("enabled", True) is False:
            continue
        if method == "rule":
            scores = run_rule_baseline(test_frame)
            threshold = float(baseline.get("threshold", 0.5))
            metrics = compute_classification_metrics(y_true, scores, threshold=threshold)
            rows.append(
                _aggregate_metric_row(
                    family,
                    method,
                    metrics,
                    metrics_payload,
                    wrapper_audit=_wrapper_audit_status(metrics_payload, method),
                )
            )
        elif method == "promptguard":
            raise ValueError(
                "PromptGuard must not be included in model-only aggregate configs; "
                "run the full eval config when fresh PromptGuard rows are required."
            )
    return rows


def _aggregate_metric_row(
    family: str,
    method: str,
    metrics: dict[str, Any],
    metrics_payload: dict[str, Any],
    *,
    stale: bool = False,
    wrapper_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "family": family,
        "method": method,
        "scope": "group_holdout_all_test_rows_previous_artifact" if stale else "group_holdout_all_test_rows_current_artifact",
        "support": metrics.get("support"),
        "positives": metrics.get("positives"),
        "negatives": metrics.get("negatives"),
        "accuracy": metrics.get("accuracy"),
        "balanced_accuracy": metrics.get("balanced_accuracy"),
        "precision": metrics.get("precision"),
        "recall": metrics.get("recall"),
        "f1": metrics.get("f1"),
        "f1_ci95_low": None,
        "f1_ci95_high": None,
        "roc_auc": metrics.get("roc_auc"),
        "pr_auc": metrics.get("pr_auc"),
        "balanced_confounder_f1": None,
        "paired_confounder_accuracy": None,
        "claim_status": metrics_payload.get("claim_readiness", {}).get("status"),
        "shortcut_risks": ";".join(
            str(risk.get("feature", "")) for risk in metrics_payload.get("shortcut_feature_risks", [])
        ),
    }
    if wrapper_audit is not None:
        row.update(wrapper_audit)
    return row


def _target_family_focus_rows(
    family: str,
    eval_config: dict[str, Any],
    metrics_payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    features = pd.read_parquet(resolve_path(eval_config["features_path"]))
    labels = pd.read_parquet(resolve_path(eval_config["labels_path"]))
    splits = load_splits(resolve_path(eval_config["splits_path"]))
    merged = labels.merge(features, on="pdf_id", how="inner", validate="one_to_one")
    test_frame = merged[merged["pdf_id"].isin(splits["test_ids"])].copy().reset_index(drop=True)

    target_mask = (test_frame["label"].astype(int) == 1) & (test_frame["attack_family"].astype(str) == family)
    negative_mask = test_frame["label"].astype(int) == 0
    focus_frame = test_frame.loc[target_mask | negative_mask].copy().reset_index(drop=True)
    y_true = focus_frame["label"].astype(int).to_numpy()

    matched_family = MATCHED_CONFOUNDER_FAMILY.get(family)
    matched_negative_mask = (
        (test_frame["label"].astype(int) == 0)
        & (test_frame["benign_confounder_family"].astype(str) == matched_family)
    )
    matched_frame = test_frame.loc[target_mask | matched_negative_mask].copy().reset_index(drop=True)
    matched_y_true = matched_frame["label"].astype(int).to_numpy()

    target_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []
    for entry in eval_config.get("model_artifacts", []):
        method = str(entry["name"])
        artifact = load_model_artifact(entry["path"])
        scores = predict_scores(artifact, focus_frame)
        threshold = float(artifact.get("threshold", 0.5))
        target_rows.append(
            _focus_row(
                family,
                method,
                "target_family_positives_vs_all_test_negatives",
                y_true,
                scores,
                threshold,
                wrapper_audit=_wrapper_audit_status(metrics_payload, method),
            )
        )
        if not matched_frame.empty and len(np.unique(matched_y_true)) == 2:
            matched_scores = predict_scores(artifact, matched_frame)
            matched_rows.append(
                _focus_row(
                    family,
                    method,
                    "target_family_positives_vs_matched_confounder",
                    matched_y_true,
                    matched_scores,
                    threshold,
                    matched_confounder_family=matched_family,
                    paired_ranking=_paired_ranking_metrics(
                        matched_frame,
                        matched_scores,
                        family,
                        matched_family,
                    ),
                    wrapper_audit=_wrapper_audit_status(metrics_payload, method),
                )
            )

    for baseline in eval_config.get("baselines", []):
        method = str(baseline.get("name", ""))
        if method != "rule" or baseline.get("enabled", True) is False:
            continue
        scores = run_rule_baseline(focus_frame)
        threshold = float(baseline.get("threshold", 0.5))
        target_rows.append(
            _focus_row(
                family,
                method,
                "target_family_positives_vs_all_test_negatives",
                y_true,
                scores,
                threshold,
                wrapper_audit=_wrapper_audit_status(metrics_payload, method),
            )
        )
        if not matched_frame.empty and len(np.unique(matched_y_true)) == 2:
            matched_scores = run_rule_baseline(matched_frame)
            matched_rows.append(
                _focus_row(
                    family,
                    method,
                    "target_family_positives_vs_matched_confounder",
                    matched_y_true,
                    matched_scores,
                    threshold,
                    matched_confounder_family=matched_family,
                    paired_ranking=_paired_ranking_metrics(
                        matched_frame,
                        matched_scores,
                        family,
                        matched_family,
                    ),
                    wrapper_audit=_wrapper_audit_status(metrics_payload, method),
                )
            )

    return {"target": target_rows, "matched": matched_rows}


def _focus_row(
    family: str,
    method: str,
    scope: str,
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    matched_confounder_family: str | None = None,
    paired_ranking: dict[str, Any] | None = None,
    wrapper_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = compute_classification_metrics(y_true, scores, threshold=threshold)
    row = {
        "family": family,
        "method": method,
        "scope": scope,
        "support": metrics.get("support"),
        "positives": metrics.get("positives"),
        "negatives": metrics.get("negatives"),
        "accuracy": metrics.get("accuracy"),
        "balanced_accuracy": metrics.get("balanced_accuracy"),
        "precision": metrics.get("precision"),
        "recall": metrics.get("recall"),
        "f1": metrics.get("f1"),
        "roc_auc": metrics.get("roc_auc"),
        "pr_auc": metrics.get("pr_auc"),
    }
    if matched_confounder_family is not None:
        row["matched_confounder_family"] = matched_confounder_family
    if paired_ranking is not None:
        row.update(
            {
                "paired_rank_pair_count": paired_ranking["pair_count"],
                "paired_rank_accuracy": paired_ranking["pair_accuracy"],
                "paired_rank_mean_margin": paired_ranking["mean_margin"],
                "paired_rank_median_margin": paired_ranking["median_margin"],
                "paired_rank_group_column": paired_ranking["group_column"],
            }
        )
    if wrapper_audit is not None:
        row.update(wrapper_audit)
    return row


def _wrapper_audit_status(metrics_payload: dict[str, Any], method: str) -> dict[str, Any]:
    if method not in {"text_tfidf", "hybrid"}:
        return {
            "wrapper_audit_status": "not_applicable",
            "wrapper_token_hit_count": None,
            "wrapper_strip_f1_drop": None,
            "synthetic_phrase_strip_f1_drop": None,
        }
    payload = metrics_payload.get("models", {}).get(method, {})
    feature_audit = payload.get("feature_weight_audit") or {}
    strip_ablation = payload.get("wrapper_token_ablation") or {}
    synthetic_ablation = payload.get("synthetic_phrase_ablation") or {}
    hit_count = feature_audit.get("wrapper_token_hit_count")
    f1_drop = strip_ablation.get("f1_drop")
    synthetic_f1_drop = synthetic_ablation.get("f1_drop")
    if hit_count is None or f1_drop is None or synthetic_f1_drop is None:
        status = "missing"
    elif int(hit_count) == 0 and float(f1_drop) <= 0.05 and float(synthetic_f1_drop) <= 0.10:
        status = "passed"
    else:
        status = "failed"
    return {
        "wrapper_audit_status": status,
        "wrapper_token_hit_count": hit_count,
        "wrapper_strip_f1_drop": f1_drop,
        "synthetic_phrase_strip_f1_drop": synthetic_f1_drop,
    }


def _paired_ranking_metrics(
    frame: pd.DataFrame,
    scores: np.ndarray,
    family: str,
    matched_confounder_family: str | None,
) -> dict[str, Any]:
    if matched_confounder_family is None:
        return _empty_paired_ranking()
    group_column = "triad_id" if "triad_id" in frame.columns else "pair_id" if "pair_id" in frame.columns else "base_pdf_id"
    scored = frame.copy()
    scored["score"] = np.asarray(scores, dtype=float)
    margins: list[float] = []

    for _, group in scored.groupby(group_column, sort=False):
        injected_mask = (group["label"].astype(int) == 1) & (group["attack_family"].astype(str) == family)
        confounder_mask = (
            (group["label"].astype(int) == 0)
            & (group["benign_confounder_family"].astype(str) == matched_confounder_family)
        )
        if "pdf_role" in group.columns:
            injected_mask = injected_mask & (group["pdf_role"].astype(str) == "injected_attack")
            confounder_mask = confounder_mask & (group["pdf_role"].astype(str) == "benign_confounder")
        injected_scores = group.loc[injected_mask, "score"]
        confounder_scores = group.loc[confounder_mask, "score"]
        if len(injected_scores) != 1 or len(confounder_scores) != 1:
            continue
        margins.append(float(injected_scores.iloc[0]) - float(confounder_scores.iloc[0]))

    if not margins:
        result = _empty_paired_ranking()
        result["group_column"] = group_column
        return result

    margins_array = np.asarray(margins, dtype=float)
    return {
        "pair_count": int(len(margins)),
        "pair_accuracy": float(np.mean(margins_array > 0.0)),
        "mean_margin": float(np.mean(margins_array)),
        "median_margin": float(np.median(margins_array)),
        "group_column": group_column,
    }


def _empty_paired_ranking() -> dict[str, Any]:
    return {
        "pair_count": 0,
        "pair_accuracy": None,
        "mean_margin": None,
        "median_margin": None,
        "group_column": None,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
