from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_like: Any, base_dir: Path | None = None) -> Path:
    if isinstance(path_like, Path):
        path = path_like
    else:
        path = Path(str(path_like))
    if path.is_absolute():
        return path
    root = base_dir or PROJECT_ROOT
    return (root / path).resolve()


def load_yaml_config(path_like: Any) -> dict[str, Any]:
    path = resolve_path(path_like)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping config at {path}")
    return data


def ensure_parent(path_like: Any) -> Path:
    path = resolve_path(path_like)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path_like: Any) -> Any:
    path = resolve_path(path_like)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(payload: Any, path_like: Any) -> Path:
    path = ensure_parent(path_like)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def write_jsonl(records: Iterable[dict[str, Any]], path_like: Any) -> Path:
    path = ensure_parent(path_like)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
    return path


def utc_timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_divide(numerator: float | int, denominator: float | int) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def safe_mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def safe_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = safe_mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return float(math.sqrt(variance))


def coerce_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

