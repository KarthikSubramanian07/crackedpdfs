from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ATTACK_FAMILIES = [
    "steganographic_acrostic",
    "microglyph_steganography",
    "semantic_fragmentation",
    "layout_mimicry",
    "margin_microtext",
    "in_page_low_contrast_text",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate held-out attack-family evaluation configs.")
    parser.add_argument("--families", nargs="*", default=DEFAULT_ATTACK_FAMILIES)
    parser.add_argument("--output-dir", default="configs/holdout_attack_families")
    parser.add_argument("--dataset-template", default="configs/dataset_hard_provenance.yaml")
    parser.add_argument("--features-template", default="configs/features_hard_provenance.yaml")
    parser.add_argument("--eval-template", default="configs/eval_hard_provenance.yaml")
    parser.add_argument("--model-only-eval-template", default="configs/eval_hard_provenance_model_only.yaml")
    parser.add_argument("--logreg-template", default="configs/model_logreg_hard_provenance.yaml")
    parser.add_argument("--xgb-template", default="configs/model_xgb_hard_provenance.yaml")
    parser.add_argument("--logreg-shortcut-free-template", default="configs/model_logreg_hard_provenance_shortcut_free.yaml")
    parser.add_argument("--xgb-shortcut-free-template", default="configs/model_xgb_hard_provenance_shortcut_free.yaml")
    parser.add_argument("--text-tfidf-template", default="configs/model_text_tfidf_hard_provenance.yaml")
    parser.add_argument("--hybrid-template", default="configs/model_hybrid_hard_provenance.yaml")
    parser.add_argument("--shared-features-path", default="data/processed/hard_provenance/features.parquet")
    parser.add_argument("--shared-labels-path", default="data/processed/hard_provenance/labels.parquet")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_template = _load_yaml(args.dataset_template)
    features_template = _load_yaml(args.features_template)
    eval_template = _load_yaml(args.eval_template)
    model_only_eval_template = _load_yaml(args.model_only_eval_template)
    model_templates = {
        "logreg": _load_yaml(args.logreg_template),
        "xgb": _load_yaml(args.xgb_template),
        "logreg_shortcut_free": _load_yaml(args.logreg_shortcut_free_template),
        "xgb_shortcut_free": _load_yaml(args.xgb_shortcut_free_template),
        "text_tfidf": _load_yaml(args.text_tfidf_template),
        "hybrid": _load_yaml(args.hybrid_template),
    }

    manifest: list[dict[str, str]] = []
    for family in args.families:
        slug = _slugify(family)
        processed_dir = f"data/processed/holdout_attack_family/{slug}"
        artifacts_dir = f"data/artifacts/holdout_attack_family/{slug}"

        dataset_config = deepcopy(dataset_template)
        dataset = dataset_config["dataset"]
        dataset["canonical_metadata_output_path"] = f"{processed_dir}/canonical_metadata.jsonl"
        dataset["canonical_metadata_parquet_path"] = f"{processed_dir}/canonical_metadata.parquet"
        dataset["labels_output_path"] = f"{processed_dir}/labels.parquet"
        dataset["split_output_path"] = f"{processed_dir}/splits.json"
        dataset["validation_report_path"] = f"{artifacts_dir}/logs/dataset_validation.json"
        dataset["split"] = {
            "strategy": "heldout_attack_family",
            "heldout_column": "attack_family",
            "heldout_values": [family],
            "train_size": 0.8,
            "val_size": 0.1,
            "test_size": 0.1,
        }

        features_config = deepcopy(features_template)
        features_config["dataset_config"] = _posix_path(output_dir / f"dataset_{slug}.yaml")
        features_config["output_features_path"] = f"{processed_dir}/features.parquet"
        features_config["output_labels_path"] = f"{processed_dir}/labels.parquet"
        features_config["output_canonical_metadata_path"] = f"{processed_dir}/canonical_metadata.parquet"
        features_config["feature_schema_output_path"] = f"{artifacts_dir}/feature_schema.json"

        model_paths: dict[str, str] = {}
        model_config_paths: dict[str, str] = {}
        for model_name, template in model_templates.items():
            model_config = deepcopy(template)
            model_config["dataset_config"] = _posix_path(output_dir / f"dataset_{slug}.yaml")
            model_config["features_config"] = _posix_path(output_dir / f"features_{slug}.yaml")
            model_config["features_path"] = args.shared_features_path
            model_config["labels_path"] = args.shared_labels_path
            model_config["splits_path"] = f"{processed_dir}/splits.json"
            model_config["output_model_path"] = f"{artifacts_dir}/models/{model_name}.pkl"
            model_config["output_metrics_path"] = f"{artifacts_dir}/metrics/{model_name}_train_metrics.json"
            path = output_dir / f"model_{model_name}_{slug}.yaml"
            _write_yaml(model_config, path)
            model_paths[model_name] = model_config["output_model_path"]
            model_config_paths[model_name] = _posix_path(path)

        eval_config = deepcopy(eval_template)
        eval_config["dataset_config"] = _posix_path(output_dir / f"dataset_{slug}.yaml")
        eval_config["features_path"] = args.shared_features_path
        eval_config["labels_path"] = args.shared_labels_path
        eval_config["splits_path"] = f"{processed_dir}/splits.json"
        eval_config["artifacts_dir"] = artifacts_dir
        for entry in eval_config.get("model_artifacts", []):
            name = entry["name"]
            entry["path"] = model_paths[name]
            entry["training_config"] = model_config_paths[name]

        dataset_path = output_dir / f"dataset_{slug}.yaml"
        features_path = output_dir / f"features_{slug}.yaml"
        eval_path = output_dir / f"eval_{slug}.yaml"
        model_only_eval_config = deepcopy(model_only_eval_template)
        model_only_eval_config["dataset_config"] = _posix_path(output_dir / f"dataset_{slug}.yaml")
        model_only_eval_config["features_path"] = args.shared_features_path
        model_only_eval_config["labels_path"] = args.shared_labels_path
        model_only_eval_config["splits_path"] = f"{processed_dir}/splits.json"
        model_only_eval_config["artifacts_dir"] = artifacts_dir
        for entry in model_only_eval_config.get("model_artifacts", []):
            name = entry["name"]
            entry["path"] = model_paths[name]
            entry["training_config"] = model_config_paths[name]
        model_only_eval_path = output_dir / f"eval_model_only_{slug}.yaml"
        _write_yaml(dataset_config, dataset_path)
        _write_yaml(features_config, features_path)
        _write_yaml(eval_config, eval_path)
        _write_yaml(model_only_eval_config, model_only_eval_path)

        manifest.append(
            {
                "attack_family": family,
                "dataset_config": _posix_path(dataset_path),
                "features_config": _posix_path(features_path),
                "eval_config": _posix_path(eval_path),
                "model_only_eval_config": _posix_path(model_only_eval_path),
            }
        )

    _write_yaml({"holdouts": manifest}, output_dir / "manifest.yaml")
    print(f"generated {len(manifest)} held-out attack-family config sets under {output_dir}")


def _load_yaml(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _write_yaml(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower()).strip("_")


def _posix_path(path: Path) -> str:
    return path.as_posix()


if __name__ == "__main__":
    main()
