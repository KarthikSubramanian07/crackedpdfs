from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the reproducibility bundle embedded in final metrics without rerunning evaluation."
    )
    parser.add_argument("--config", default="configs/eval_publication_final.yaml")
    parser.add_argument("--metrics", default="data/artifacts/publication_final/metrics/metrics.json")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def copy_if_present(copied: dict[str, str], bundle_dir: Path, bundle_name: str, source: str | Path | None) -> None:
    if source is None:
        return
    source_path = resolve_path(source)
    if not source_path.exists():
        return
    dest = bundle_dir / bundle_name
    shutil.copy2(source_path, dest)
    copied[bundle_name] = str(dest)


def model_command_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("name", "")).lower()
    if "xgb" in name:
        return "xgb"
    if "text_tfidf" in name or name == "text":
        return "text"
    if "hybrid" in name:
        return "hybrid"
    return "logreg"


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    metrics_path = resolve_path(args.metrics)
    eval_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    artifacts_dir = resolve_path(eval_config["artifacts_dir"])
    bundle_dir = artifacts_dir / "reproducibility"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    copied: dict[str, str] = {}
    copy_if_present(copied, bundle_dir, "eval_config.yaml", config_path)
    copy_if_present(copied, bundle_dir, "dataset_config.yaml", eval_config.get("dataset_config"))
    copy_if_present(copied, bundle_dir, "splits.json", eval_config.get("splits_path"))
    copy_if_present(copied, bundle_dir, "feature_schema.json", eval_config.get("feature_schema_path"))
    for entry in eval_config.get("model_artifacts", []):
        training_config = entry.get("training_config")
        if training_config:
            safe_name = str(entry.get("name", "model")).replace("/", "_").replace("\\", "_")
            copy_if_present(copied, bundle_dir, f"model_{safe_name}_training_config.yaml", training_config)

    hashed_files: dict[str, Path] = {
        "features": resolve_path(eval_config["features_path"]),
        "labels": resolve_path(eval_config["labels_path"]),
        "splits": resolve_path(eval_config["splits_path"]),
    }
    for bundle_name, copied_path in copied.items():
        hashed_files[f"bundle:{bundle_name}"] = Path(copied_path)

    exact_commands = list(
        eval_config.get("exact_commands")
        or [
            f"python -m src.cli validate-dataset --config {eval_config.get('dataset_config')}",
            f"python -m src.cli build-splits --config {eval_config.get('dataset_config')}",
            "python -m src.cli build-features --config <features_config>",
            *[
                f"python -m src.cli train --model {model_command_name(entry)} --config {entry.get('training_config')}"
                for entry in eval_config.get("model_artifacts", [])
                if entry.get("training_config")
            ],
            f"python -m src.cli evaluate --config {config_path}",
        ]
    )
    repro_bundle = {
        "bundle_dir": str(bundle_dir),
        "copied_files": copied,
        "file_hashes": {
            name: sha256_file(path)
            for name, path in hashed_files.items()
            if path.exists() and path.is_file()
        },
        "exact_commands": exact_commands,
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
    manifest = dict(repro_bundle)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    repro_bundle["manifest_path"] = str(manifest_path)
    metrics["reproducibility_bundle"] = repro_bundle
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    schema_hash = repro_bundle["file_hashes"].get("bundle:feature_schema.json")
    print(json.dumps({"metrics": str(metrics_path), "feature_schema_hash": schema_hash}, indent=2))


if __name__ == "__main__":
    main()
