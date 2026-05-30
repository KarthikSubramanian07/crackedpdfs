from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import load_config
from .fonts import FONT_DEFINITIONS
from .templates import resolve_templates


DEFAULT_BENIGN_FIELDS = (
    "source_type",
    "template_id",
    "font_family",
    "page_size",
    "margin_preset",
    "density_preset",
    "has_header",
    "has_footer",
    "has_small_text",
    "column_mode",
    "has_table_region",
    "seed",
)

DEFAULT_COMMON_FIELDS = (
    "doc_id",
    "status",
    "pdf_path",
    "page_count",
)


@dataclass(frozen=True)
class SupportThresholds:
    min_family_count: int
    min_template_count: int
    min_regime_count: int


@dataclass(frozen=True)
class DistributionLimits:
    max_family_share: float
    max_template_share: float
    max_regime_share: float


@dataclass(frozen=True)
class NearDuplicateConfig:
    similarity_threshold: float
    shingle_size: int
    band_count: int
    rows_per_band: int
    max_bucket_size: int
    sample_limit: int

    @property
    def permutation_count(self) -> int:
        return self.band_count * self.rows_per_band


@dataclass(frozen=True)
class AuditExpectations:
    families: tuple[str, ...]
    templates: tuple[str, ...]
    fonts: tuple[str, ...]
    page_sizes: tuple[str, ...]
    margin_presets: tuple[str, ...]
    density_presets: tuple[str, ...]


@dataclass(frozen=True)
class AuditConfig:
    profile: str
    config_path: Path
    stage_field: str
    default_stage: str
    allow_missing_stage_for_default: bool
    allowed_stages: tuple[str, ...]
    allowed_statuses: tuple[str, ...]
    regime_field: str
    parent_field: str
    allowed_regimes: tuple[str, ...]
    required_common_fields: tuple[str, ...]
    required_stage_fields: dict[str, tuple[str, ...]]
    expectations: AuditExpectations
    support_thresholds: SupportThresholds
    distribution_limits: DistributionLimits
    near_duplicate: NearDuplicateConfig
    suspicious_keywords: tuple[str, ...]


def _resolve_path(base_path: Path, raw_value: str | None) -> Path | None:
    if not raw_value:
        return None
    path = Path(raw_value)
    if path.is_absolute():
        return path
    return (base_path.parent / path).resolve()


def _normalize_probability(value: Any, name: str) -> float:
    numeric = float(value)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {numeric}")
    return numeric


def _normalize_positive_int(value: Any, name: str, *, minimum: int = 1) -> int:
    numeric = int(value)
    if numeric < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {numeric}")
    return numeric


def _normalize_tuple(values: list[Any] | tuple[Any, ...] | None, default: tuple[str, ...], name: str) -> tuple[str, ...]:
    raw_values = values if values is not None else list(default)
    if not raw_values:
        raise ValueError(f"{name} must not be empty")
    return tuple(str(value) for value in raw_values)


def _expectations_from_generator_config(generator_config_path: Path) -> AuditExpectations:
    generator_config = load_config(generator_config_path)
    templates = [
        template
        for template in resolve_templates(generator_config.template_allowlist)
        if generator_config.family_weights.get(template.source_type, 0) > 0
    ]
    return AuditExpectations(
        families=tuple(sorted({template.source_type for template in templates})),
        templates=tuple(sorted(template.template_id for template in templates)),
        fonts=tuple(sorted(FONT_DEFINITIONS[key].display_name for key in generator_config.font_allowlist)),
        page_sizes=tuple(sorted(page_size for page_size, weight in generator_config.page_size_weights.items() if weight > 0)),
        margin_presets=tuple(generator_config.margin_presets),
        density_presets=tuple(generator_config.density_presets),
    )


def load_audit_config(config_path: str | Path) -> AuditConfig:
    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    profile = str(raw.get("profile", "benign_only")).strip().lower()
    if profile not in {"benign_only", "mixed"}:
        raise ValueError(f"profile must be 'benign_only' or 'mixed', got {profile}")

    generator_config_path = _resolve_path(path, raw.get("generator_config_path"))
    expected_raw = raw.get("expected", {}) or {}
    if generator_config_path:
        expectations = _expectations_from_generator_config(generator_config_path)
    else:
        expectations = AuditExpectations(
            families=_normalize_tuple(expected_raw.get("families"), tuple(), "expected.families"),
            templates=_normalize_tuple(expected_raw.get("templates"), tuple(), "expected.templates"),
            fonts=_normalize_tuple(expected_raw.get("fonts"), tuple(), "expected.fonts"),
            page_sizes=_normalize_tuple(expected_raw.get("page_sizes"), tuple(), "expected.page_sizes"),
            margin_presets=_normalize_tuple(expected_raw.get("margin_presets"), tuple(), "expected.margin_presets"),
            density_presets=_normalize_tuple(expected_raw.get("density_presets"), tuple(), "expected.density_presets"),
        )

    allowed_stages_default = ("benign",) if profile == "benign_only" else ("benign", "injected")
    allowed_stages = _normalize_tuple(raw.get("allowed_stages"), allowed_stages_default, "allowed_stages")
    stage_field = str(raw.get("stage_field", "stage"))
    default_stage = str(raw.get("default_stage", "benign"))
    allow_missing_stage_for_default = bool(raw.get("allow_missing_stage_for_default", profile == "benign_only"))
    regime_field = str(raw.get("regime_field", "regime"))
    parent_field = str(raw.get("parent_field", "parent_doc_id"))
    allowed_regimes = tuple(str(value) for value in raw.get("allowed_regimes", []))
    allowed_statuses = _normalize_tuple(raw.get("allowed_statuses"), ("generated",), "allowed_statuses")
    required_common_fields = _normalize_tuple(
        raw.get("required_common_fields"),
        DEFAULT_COMMON_FIELDS,
        "required_common_fields",
    )

    required_stage_fields_raw = raw.get("required_stage_fields", {}) or {}
    benign_fields = _normalize_tuple(
        required_stage_fields_raw.get("benign"),
        DEFAULT_BENIGN_FIELDS,
        "required_stage_fields.benign",
    )
    injected_fields_default = tuple(list(DEFAULT_BENIGN_FIELDS) + [parent_field, regime_field])
    injected_fields = _normalize_tuple(
        required_stage_fields_raw.get("injected"),
        injected_fields_default,
        "required_stage_fields.injected",
    )

    support_raw = raw.get("support_thresholds", {}) or {}
    distribution_raw = raw.get("distribution_limits", {}) or {}
    near_duplicate_raw = raw.get("near_duplicate", {}) or {}

    suspicious_keywords = tuple(
        str(value)
        for value in raw.get(
            "suspicious_keywords",
            [
                "ignore previous",
                "system prompt",
                "prompt injection",
                "developer message",
                "follow these instructions",
                "jailbreak",
            ],
        )
    )

    return AuditConfig(
        profile=profile,
        config_path=path,
        stage_field=stage_field,
        default_stage=default_stage,
        allow_missing_stage_for_default=allow_missing_stage_for_default,
        allowed_stages=allowed_stages,
        allowed_statuses=allowed_statuses,
        regime_field=regime_field,
        parent_field=parent_field,
        allowed_regimes=allowed_regimes,
        required_common_fields=required_common_fields,
        required_stage_fields={
            "benign": benign_fields,
            "injected": injected_fields,
        },
        expectations=expectations,
        support_thresholds=SupportThresholds(
            min_family_count=_normalize_positive_int(support_raw.get("min_family_count", 25), "support_thresholds.min_family_count"),
            min_template_count=_normalize_positive_int(support_raw.get("min_template_count", 10), "support_thresholds.min_template_count"),
            min_regime_count=_normalize_positive_int(support_raw.get("min_regime_count", 25), "support_thresholds.min_regime_count"),
        ),
        distribution_limits=DistributionLimits(
            max_family_share=_normalize_probability(distribution_raw.get("max_family_share", 0.30), "distribution_limits.max_family_share"),
            max_template_share=_normalize_probability(distribution_raw.get("max_template_share", 0.18), "distribution_limits.max_template_share"),
            max_regime_share=_normalize_probability(distribution_raw.get("max_regime_share", 0.30), "distribution_limits.max_regime_share"),
        ),
        near_duplicate=NearDuplicateConfig(
            similarity_threshold=_normalize_probability(near_duplicate_raw.get("similarity_threshold", 0.94), "near_duplicate.similarity_threshold"),
            shingle_size=_normalize_positive_int(near_duplicate_raw.get("shingle_size", 5), "near_duplicate.shingle_size"),
            band_count=_normalize_positive_int(near_duplicate_raw.get("band_count", 6), "near_duplicate.band_count"),
            rows_per_band=_normalize_positive_int(near_duplicate_raw.get("rows_per_band", 4), "near_duplicate.rows_per_band"),
            max_bucket_size=_normalize_positive_int(near_duplicate_raw.get("max_bucket_size", 200), "near_duplicate.max_bucket_size"),
            sample_limit=_normalize_positive_int(near_duplicate_raw.get("sample_limit", 25), "near_duplicate.sample_limit"),
        ),
        suspicious_keywords=suspicious_keywords,
    )
