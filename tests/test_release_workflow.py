from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_frozen_fixture(root: Path) -> Path:
    artifacts = root / "artifacts"
    (artifacts / "metrics").mkdir(parents=True)
    (artifacts / "features.parquet").write_bytes(b"frozen features\n")
    (artifacts / "labels.parquet").write_bytes(b"frozen labels\n")
    (artifacts / "splits.json").write_text(
        json.dumps({"train": ["base-a"], "val": ["base-b"], "test": ["base-c"]}),
        encoding="utf-8",
    )
    metrics = {
        "split_strategy": "heldout_provenance",
        "models": {
            "tiny_model": {
                "metrics": {
                    "accuracy": 0.9,
                    "precision": 0.8,
                    "recall": 0.7,
                    "f1": 0.746,
                    "roc_auc": 0.91,
                    "pr_auc": 0.89,
                },
                "sanity_checks": {
                    "label_shuffle": {
                        "accuracy": 0.5,
                        "precision": 0.4,
                        "recall": 0.3,
                        "f1": 0.343,
                        "roc_auc": 0.51,
                        "pr_auc": 0.49,
                    }
                },
            }
        },
        "baselines": {
            "rule": {
                "metrics": {
                    "accuracy": 0.6,
                    "precision": 0.55,
                    "recall": 0.5,
                    "f1": 0.524,
                    "roc_auc": 0.62,
                    "pr_auc": 0.58,
                }
            }
        },
    }
    (artifacts / "metrics" / "metrics.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )

    files = []
    for relative in (
        "features.parquet",
        "labels.parquet",
        "splits.json",
        "metrics/metrics.json",
    ):
        path = artifacts / relative
        files.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        )
    manifest = root / "download-manifest.json"
    manifest.write_text(json.dumps({"files": files}), encoding="utf-8")
    return manifest


def test_reproduce_results_validates_artifacts_and_regenerates_table(tmp_path: Path) -> None:
    manifest = _write_frozen_fixture(tmp_path)
    output_dir = tmp_path / "output"

    result = _run(
        "scripts/reproduce_results.py",
        "--artifact-dir",
        str(tmp_path / "artifacts"),
        "--manifest",
        str(manifest),
        "--output-dir",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    assert "Verified 4 frozen artifacts" in result.stdout
    assert (output_dir / "hard-setting-summary.csv").read_text(encoding="utf-8") == (
        "entry_type,name,setting,accuracy,precision,recall,f1,roc_auc,pr_auc\n"
        "model,tiny_model,heldout_provenance,0.9,0.8,0.7,0.746,0.91,0.89\n"
        "baseline,rule,heldout_provenance,0.6,0.55,0.5,0.524,0.62,0.58\n"
        "sanity_check,tiny_model,label_shuffle,0.5,0.4,0.3,0.343,0.51,0.49\n"
    )


def test_reproduce_results_rejects_tampered_artifact(tmp_path: Path) -> None:
    manifest = _write_frozen_fixture(tmp_path)
    (tmp_path / "artifacts" / "labels.parquet").write_bytes(b"tampered\n")

    result = _run(
        "scripts/reproduce_results.py",
        "--artifact-dir",
        str(tmp_path / "artifacts"),
        "--manifest",
        str(manifest),
        "--output-dir",
        str(tmp_path / "output"),
    )

    assert result.returncode != 0
    assert "SHA-256 mismatch for labels.parquet" in result.stderr


def test_source_snapshot_verifier_ignores_bytecode_and_catches_source_drift(
    tmp_path: Path,
) -> None:
    detector = tmp_path / "lightweight-detector"
    source = detector / "src" / "good.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"print('paper source')\n")
    manifest = tmp_path / "source-hashes.json"
    manifest.write_text(
        json.dumps(
            [
                {"path": ".\\src\\good.py", "sha256": _sha256(source)},
                {"path": ".\\src\\__pycache__\\good.cpython-313.pyc", "sha256": "0" * 64},
            ]
        ),
        encoding="utf-8",
    )

    valid = _run(
        "scripts/verify_source_snapshot.py",
        "--repo-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
    )
    assert valid.returncode == 0, valid.stderr
    assert "Verified 1/1 source files" in valid.stdout
    assert "Excluded 1 Python bytecode cache" in valid.stdout

    unexpected = detector / "src" / "unexpected.py"
    unexpected.write_bytes(b"print('not in the paper snapshot')\n")
    with_extra = _run(
        "scripts/verify_source_snapshot.py",
        "--repo-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
    )
    assert with_extra.returncode != 0
    assert "Unexpected source file: src/unexpected.py" in with_extra.stderr
    unexpected.unlink()

    source.write_bytes(b"print('drifted')\n")
    invalid = _run(
        "scripts/verify_source_snapshot.py",
        "--repo-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
    )
    assert invalid.returncode != 0
    assert "SHA-256 mismatch for src/good.py" in invalid.stderr


def test_smoke_benchmark_creates_valid_benign_and_injected_pdfs(tmp_path: Path) -> None:
    result = _run("scripts/smoke_benchmark.py", "--output-dir", str(tmp_path / "smoke"))

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["generated_count"] == 1
    assert report["injected_count"] == 1
    assert Path(report["benign_pdf"]).is_file()
    assert Path(report["injected_pdf"]).is_file()
    assert report["attack_stats"]["segment_count"] >= 1
