from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .fonts import FONT_DEFINITIONS, canonicalize_font_key
from .models import DENSITY_PROFILES, KNOWN_SOURCE_TYPES, MARGIN_PRESETS, PAGE_SIZE_POINTS


@dataclass(frozen=True)
class GeneratorConfig:
    output_root: Path
    total_count: int
    seed: int
    resume_mode: str
    family_weights: dict[str, float]
    template_allowlist: list[str]
    page_size_weights: dict[str, float]
    margin_presets: list[str]
    density_presets: list[str]
    font_allowlist: list[str]
    header_probability: float
    footer_probability: float
    small_text_probability: float
    table_region_probability: float

    @property
    def base_output_dir(self) -> Path:
        return self.output_root / "base"

    @property
    def manifest_path(self) -> Path:
        return self.output_root / "manifest.jsonl"


def _validate_probability(value: float, name: str) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")
    return value


def _normalize_weights(values: dict[str, Any], allowed: set[str], name: str) -> dict[str, float]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    normalized: dict[str, float] = {}
    for key, raw_value in values.items():
        if key not in allowed:
            raise ValueError(f"Unknown {name} key: {key}")
        weight = float(raw_value)
        if weight < 0:
            raise ValueError(f"{name} weights must be non-negative, got {weight} for {key}")
        normalized[key] = weight
    if not any(weight > 0 for weight in normalized.values()):
        raise ValueError(f"{name} must contain at least one positive weight")
    return normalized


def _normalize_sequence(values: list[str], allowed: set[str], name: str) -> list[str]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    normalized: list[str] = []
    for value in values:
        if value not in allowed:
            raise ValueError(f"Unknown {name} value: {value}")
        normalized.append(value)
    return normalized


def load_config(config_path: str | Path) -> GeneratorConfig:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    output_root = Path(raw.get("output_root", "out"))
    total_count = int(raw.get("total_count", 100))
    if total_count <= 0:
        raise ValueError("total_count must be positive")

    seed = int(raw.get("seed", 20260320))
    resume_mode = str(raw.get("resume_mode", "skip")).lower()
    if resume_mode not in {"skip", "overwrite"}:
        raise ValueError("resume_mode must be 'skip' or 'overwrite'")

    family_defaults = {family: 1.0 for family in KNOWN_SOURCE_TYPES}
    family_weights = _normalize_weights(
        raw.get("family_weights", family_defaults),
        set(KNOWN_SOURCE_TYPES),
        "family_weights",
    )

    template_allowlist = [str(value) for value in raw.get("template_allowlist", [])]

    page_size_defaults = {"letter": 1.0, "a4": 1.0}
    page_size_weights = _normalize_weights(
        raw.get("page_size_weights", page_size_defaults),
        set(PAGE_SIZE_POINTS),
        "page_size_weights",
    )

    margin_presets = _normalize_sequence(
        [str(value) for value in raw.get("margin_presets", list(MARGIN_PRESETS))],
        set(MARGIN_PRESETS),
        "margin_presets",
    )
    density_presets = _normalize_sequence(
        [str(value) for value in raw.get("density_presets", list(DENSITY_PROFILES))],
        set(DENSITY_PROFILES),
        "density_presets",
    )

    raw_fonts = raw.get("font_allowlist", list(FONT_DEFINITIONS))
    font_allowlist = [canonicalize_font_key(str(value)) for value in raw_fonts]

    return GeneratorConfig(
        output_root=output_root,
        total_count=total_count,
        seed=seed,
        resume_mode=resume_mode,
        family_weights=family_weights,
        template_allowlist=template_allowlist,
        page_size_weights=page_size_weights,
        margin_presets=margin_presets,
        density_presets=density_presets,
        font_allowlist=font_allowlist,
        header_probability=_validate_probability(
            float(raw.get("header_probability", 0.72)), "header_probability"
        ),
        footer_probability=_validate_probability(
            float(raw.get("footer_probability", 0.56)), "footer_probability"
        ),
        small_text_probability=_validate_probability(
            float(raw.get("small_text_probability", 0.34)), "small_text_probability"
        ),
        table_region_probability=_validate_probability(
            float(raw.get("table_region_probability", 0.8)), "table_region_probability"
        ),
    )
