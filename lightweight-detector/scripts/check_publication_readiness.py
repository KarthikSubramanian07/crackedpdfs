from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-hard publication readiness gate.")
    parser.add_argument("--metrics", default="data/artifacts/publication_final/metrics/metrics.json")
    parser.add_argument("--config", default="configs/eval_publication_final.yaml")
    parser.add_argument("--primary-model", default="hybrid")
    parser.add_argument("--min-f1", type=float, default=0.75)
    parser.add_argument("--min-paired-accuracy", type=float, default=0.75)
    parser.add_argument("--min-paired-ci-low", type=float, default=0.60)
    parser.add_argument("--max-label-shuffle-f1", type=float, default=0.65)
    parser.add_argument("--max-label-shuffle-roc-auc", type=float, default=0.65)
    parser.add_argument("--require-bootstrap", action="store_true")
    parser.add_argument("--require-ablations", action="store_true")
    parser.add_argument("--require-sanity", action="store_true")
    args = parser.parse_args()

    metrics_path = Path(args.metrics)
    config_path = Path(args.config)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    failures: list[str] = []
    warnings: list[str] = []

    readiness = metrics.get("claim_readiness", {})
    if readiness.get("status") != "usable_with_caveats":
        failures.append(f"claim_readiness.status={readiness.get('status')!r}")
    failures.extend(str(item) for item in readiness.get("blockers", []) or [])

    if args.require_ablations and not bool(config.get("run_ablations")):
        failures.append("final config must set run_ablations=true")
    if args.require_sanity and not bool(config.get("run_sanity_checks")):
        failures.append("final config must set run_sanity_checks=true")
    if args.require_bootstrap and int((config.get("bootstrap") or {}).get("iterations", 0) or 0) <= 0:
        failures.append("final config must enable bootstrap iterations")
    if bool((config.get("claim_thresholds") or {}).get("fail_on_blocked")) is not True:
        failures.append("final config must set claim_thresholds.fail_on_blocked=true")

    if args.require_ablations and "ablations" not in metrics:
        failures.append("metrics missing ablations payload")

    model_payload = (metrics.get("models") or {}).get(args.primary_model)
    if not model_payload:
        failures.append(f"primary model missing from metrics: {args.primary_model}")
    else:
        _check_primary_model(
            args=args,
            payload=model_payload,
            failures=failures,
            warnings=warnings,
        )

    _check_text_like_audits(metrics, config, args.primary_model, failures, warnings)
    _check_structural_negative_framing(metrics, warnings)

    summary = {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "metrics": str(metrics_path),
        "config": str(config_path),
        "primary_model": args.primary_model,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


def _check_primary_model(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    model_metrics = payload.get("metrics") or {}
    f1 = _float_or_none(model_metrics.get("f1"))
    if f1 is None or f1 < args.min_f1:
        failures.append(f"{args.primary_model} F1 {f1} below gate {args.min_f1}")

    paired = (
        payload.get("paired_contrast", {})
        .get("by_negative_type", {})
        .get("benign_confounder", {})
    )
    pair_accuracy = _float_or_none(paired.get("pair_accuracy"))
    if pair_accuracy is None or pair_accuracy < args.min_paired_accuracy:
        failures.append(
            f"{args.primary_model} paired benign-confounder accuracy {pair_accuracy} below gate {args.min_paired_accuracy}"
        )
    ci_low = _float_or_none((paired.get("pair_accuracy_ci95") or {}).get("low"))
    if ci_low is None or ci_low < args.min_paired_ci_low:
        failures.append(
            f"{args.primary_model} paired benign-confounder CI low {ci_low} below gate {args.min_paired_ci_low}"
        )

    bootstrap = payload.get("confidence_intervals", {})
    if args.require_bootstrap and not bool(bootstrap.get("enabled")):
        failures.append(f"{args.primary_model} missing enabled bootstrap confidence intervals")

    sanity = (payload.get("sanity_checks") or {}).get("label_shuffle")
    if args.require_sanity and not sanity:
        failures.append(f"{args.primary_model} missing label-shuffle sanity check")
    elif sanity:
        shuffle_f1 = _float_or_none(sanity.get("f1"))
        if shuffle_f1 is not None and shuffle_f1 > args.max_label_shuffle_f1:
            failures.append(
                f"{args.primary_model} label-shuffle F1 {shuffle_f1:.3f} exceeds gate {args.max_label_shuffle_f1:.3f}"
            )
        shuffle_auc = _float_or_none(sanity.get("roc_auc"))
        if shuffle_auc is not None and shuffle_auc > args.max_label_shuffle_roc_auc:
            failures.append(
                f"{args.primary_model} label-shuffle ROC-AUC {shuffle_auc:.3f} exceeds gate {args.max_label_shuffle_roc_auc:.3f}"
            )

    residual_flags = (payload.get("residual_marker_audit") or {}).get("flags") or []
    if residual_flags:
        failures.append(f"{args.primary_model} residual marker audit has {len(residual_flags)} flags")

    wrapper_hits = int((payload.get("feature_weight_audit") or {}).get("wrapper_token_hit_count", 0) or 0)
    if wrapper_hits:
        failures.append(f"{args.primary_model} wrapper/synthetic top-weight hits={wrapper_hits}")

    for name in ["wrapper_token_ablation", "synthetic_phrase_ablation"]:
        ablation = payload.get(name) or {}
        if "f1_drop" not in ablation:
            failures.append(f"{args.primary_model} missing {name}.f1_drop")

    if f1 is not None and f1 > 0.99:
        warnings.append(f"{args.primary_model} F1={f1:.4f}; keep suspicious-score discussion in paper")


def _check_text_like_audits(
    metrics: dict[str, Any],
    config: dict[str, Any],
    primary_model: str,
    failures: list[str],
    warnings: list[str],
) -> None:
    text_thresholds = ((config.get("claim_thresholds") or {}).get("text_detector") or {})
    max_wrapper_hits = int(text_thresholds.get("max_wrapper_top_weight_hits", 0) or 0)
    wrapper_max_drop = _float_or_none(text_thresholds.get("max_wrapper_strip_f1_drop"))
    synthetic_max_drop = _float_or_none(text_thresholds.get("max_synthetic_phrase_strip_f1_drop"))
    wrapper_max_drop = 0.05 if wrapper_max_drop is None else wrapper_max_drop
    synthetic_max_drop = 0.10 if synthetic_max_drop is None else synthetic_max_drop
    primary_models = set(
        str(name)
        for name in ((config.get("claim_thresholds") or {}).get("primary_shortcut_free_models") or [primary_model])
    )
    for model_name, payload in (metrics.get("models") or {}).items():
        if model_name not in {"text_tfidf", "hybrid"}:
            continue
        model_failures: list[str] = []
        for key in ["feature_weight_audit", "wrapper_token_ablation", "synthetic_phrase_ablation"]:
            if key not in payload:
                model_failures.append(f"{model_name} missing text shortcut audit: {key}")
        wrapper_hits = int((payload.get("feature_weight_audit") or {}).get("wrapper_token_hit_count", 0) or 0)
        if wrapper_hits > max_wrapper_hits:
            model_failures.append(
                f"{model_name} wrapper/synthetic top-weight hits={wrapper_hits} exceeds gate {max_wrapper_hits}"
            )
        _check_ablation_drop(
            model_name,
            "wrapper_token_ablation",
            payload,
            wrapper_max_drop,
            model_failures,
        )
        _check_ablation_drop(
            model_name,
            "synthetic_phrase_ablation",
            payload,
            synthetic_max_drop,
            model_failures,
        )
        residual_flags = (payload.get("residual_marker_audit") or {}).get("flags") or []
        if residual_flags:
            model_failures.append(f"{model_name} residual marker audit has {len(residual_flags)} flags")
        if model_name in primary_models:
            failures.extend(model_failures)
        else:
            warnings.extend(f"non-primary comparator: {failure}" for failure in model_failures)


def _check_structural_negative_framing(metrics: dict[str, Any], warnings: list[str]) -> None:
    for name in ["logreg_shortcut_free", "xgb_shortcut_free"]:
        payload = (metrics.get("models") or {}).get(name)
        if not payload:
            continue
        paired = (
            payload.get("paired_contrast", {})
            .get("by_negative_type", {})
            .get("benign_confounder", {})
        )
        pair_accuracy = _float_or_none(paired.get("pair_accuracy"))
        if pair_accuracy is not None and pair_accuracy < 0.75:
            warnings.append(
                f"{name} paired benign-confounder accuracy={pair_accuracy:.3f}; frame as structural-only negative result"
            )


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_ablation_drop(
    model_name: str,
    key: str,
    payload: dict[str, Any],
    max_drop: float,
    failures: list[str],
) -> None:
    drop = _float_or_none((payload.get(key) or {}).get("f1_drop"))
    if drop is None:
        return
    if drop > max_drop:
        failures.append(f"{model_name} {key}.f1_drop={drop:.4f} exceeds gate {max_drop:.4f}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"missing required file: {exc}", file=sys.stderr)
        raise SystemExit(1)
