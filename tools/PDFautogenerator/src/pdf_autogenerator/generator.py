from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any

from .config import GeneratorConfig
from .content import load_snippet_bank
from .fonts import register_fonts
from .manifest import append_manifest_row, build_manifest_index, read_manifest
from .models import ManifestRow, PAGE_SIZE_POINTS, VariantChoices
from .rendering import build_theme, plan_fits, render_pdf
from .templates import build_document_plan, resolve_templates
from .validation import validate_generated_pdf

MAX_GENERATION_ATTEMPTS = 16
MAX_OVERFLOW_ATTEMPTS = 4


def weighted_choice(rng: Random, weighted: dict[str, float]) -> str:
    total = sum(value for value in weighted.values() if value > 0)
    target = rng.random() * total
    cumulative = 0.0
    for key, weight in weighted.items():
        if weight <= 0:
            continue
        cumulative += weight
        if cumulative >= target:
            return key
    return next(iter(weighted))


def doc_id_for(seed: int, index: int) -> str:
    return f"benign-{seed}-{index:06d}"


def largest_remainder_counts(weighted: dict[str, float], total: int) -> dict[str, int]:
    positive = {key: weight for key, weight in weighted.items() if weight > 0}
    if not positive:
        raise ValueError("At least one positive weight is required")
    total_weight = sum(positive.values())
    counts: dict[str, int] = {}
    remainders: list[tuple[float, float, str]] = []
    assigned = 0
    for key, weight in positive.items():
        exact = (weight / total_weight) * total
        count = int(exact)
        counts[key] = count
        assigned += count
        remainders.append((exact - count, weight, key))
    for key in weighted:
        counts.setdefault(key, 0)
    if assigned < total:
        remainders.sort(key=lambda item: (-item[0], -item[1], item[2]))
        for _, _, key in remainders[: total - assigned]:
            counts[key] += 1
    return counts


def build_template_schedule(config: GeneratorConfig, all_templates: list[Any]) -> list[Any]:
    templates_by_source: dict[str, list[Any]] = {}
    for template in all_templates:
        templates_by_source.setdefault(template.source_type, []).append(template)

    effective_family_weights = {
        family: weight
        for family, weight in config.family_weights.items()
        if weight > 0 and templates_by_source.get(family)
    }
    family_counts = largest_remainder_counts(effective_family_weights, config.total_count)
    schedule: list[Any] = []
    rng = Random(f"schedule:{config.seed}")
    for family, count in family_counts.items():
        if count <= 0:
            continue
        family_templates = list(templates_by_source[family])
        rng.shuffle(family_templates)
        template_counts = largest_remainder_counts(
            {template.template_id: 1.0 for template in family_templates},
            count,
        )
        family_schedule: list[Any] = []
        for template in family_templates:
            family_schedule.extend([template] * template_counts[template.template_id])
        rng.shuffle(family_schedule)
        schedule.extend(family_schedule)
    rng.shuffle(schedule)
    if len(schedule) != config.total_count:
        raise RuntimeError(
            f"Template schedule length mismatch: expected {config.total_count}, got {len(schedule)}"
        )
    return schedule


def choose_variant(
    config: GeneratorConfig,
    rng: Random,
    template,
    font_registry,
) -> VariantChoices:
    font_key = rng.choice(config.font_allowlist)
    page_size = weighted_choice(rng, config.page_size_weights)
    margin_preset = rng.choice(config.margin_presets)
    density_preset = rng.choice(config.density_presets)
    has_header = template.requires_header or (rng.random() < config.header_probability)
    has_footer = rng.random() < config.footer_probability
    has_small_text = rng.random() < config.small_text_probability
    if template.allows_two_columns:
        column_mode = "double" if rng.random() < 0.45 else "single"
    else:
        column_mode = "single"
    if template.requires_table_region:
        has_table_region = True
    elif template.supports_table_region:
        has_table_region = rng.random() < config.table_region_probability
    else:
        has_table_region = False
    font = font_registry[font_key]
    return VariantChoices(
        page_size=page_size,
        margin_preset=margin_preset,
        density_preset=density_preset,
        font_key=font_key,
        font_family=font.display_name,
        has_header=has_header,
        has_footer=has_footer,
        has_small_text=has_small_text,
        column_mode=column_mode,
        has_table_region=has_table_region,
    )


def _remove_invalid_output(path: Path | None) -> None:
    if path and path.exists():
        path.unlink()


def _prepare_output_root(config: GeneratorConfig) -> None:
    if config.resume_mode != "overwrite":
        return
    if config.manifest_path.exists():
        config.manifest_path.unlink()
    if not config.base_output_dir.exists():
        return
    for path in config.base_output_dir.glob("*.pdf"):
        path.unlink()


def generate_documents(config: GeneratorConfig) -> list[dict[str, Any]]:
    font_registry = register_fonts(config.font_allowlist)
    snippet_bank = load_snippet_bank()
    all_templates = resolve_templates(config.template_allowlist)
    _prepare_output_root(config)
    rows = read_manifest(config.manifest_path)
    manifest_index = build_manifest_index(rows)
    seen_fingerprints = {
        row["content_fingerprint"]
        for row in rows
        if row.get("content_fingerprint") and row.get("status") == "generated"
    }
    generated_rows: list[dict[str, Any]] = []
    config.base_output_dir.mkdir(parents=True, exist_ok=True)
    template_schedule = build_template_schedule(config, all_templates)

    for index in range(config.total_count):
        doc_id = doc_id_for(config.seed, index)
        existing = manifest_index.get(doc_id)
        if (
            config.resume_mode == "skip"
            and existing
            and existing.get("status") == "generated"
            and existing.get("pdf_path")
            and Path(existing["pdf_path"]).exists()
        ):
            continue

        destination = config.base_output_dir / f"{doc_id}.pdf"
        if config.resume_mode == "overwrite" and destination.exists():
            destination.unlink()

        success_row: dict[str, Any] | None = None
        last_row: ManifestRow | None = None
        scheduled_template = template_schedule[index]
        overflow_attempts = 0
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            rng = Random(f"{config.seed}:{index}:{attempt}")
            template = scheduled_template
            source_type = template.source_type
            variant = choose_variant(config, rng, template, font_registry)
            page_size = PAGE_SIZE_POINTS[variant.page_size]
            plan = build_document_plan(template, variant, snippet_bank, page_size, rng)

            if plan.content_fingerprint in seen_fingerprints:
                last_row = ManifestRow(
                    doc_id=doc_id,
                    source_type=source_type,
                    template_id=template.template_id,
                    font_family=variant.font_family,
                    layout_variant=variant.layout_variant,
                    has_header=variant.has_header,
                    has_footer=variant.has_footer,
                    has_small_text=variant.has_small_text,
                    page_size=variant.page_size,
                    margin_preset=variant.margin_preset,
                    density_preset=variant.density_preset,
                    column_mode=variant.column_mode,
                    has_table_region=variant.has_table_region,
                    seed=config.seed,
                    pdf_path=None,
                    page_count=0,
                    status="rejected",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    template_family=template.template_family,
                    generation_attempts=attempt,
                    overflow_resampled=False,
                    notes={"reason": "duplicate_fingerprint"},
                    content_fingerprint=plan.content_fingerprint,
                )
                continue

            font = font_registry[variant.font_key]
            theme = build_theme(font, variant, tighten_spacing=False)
            overflow_resampled = False
            if not plan_fits(plan, theme):
                theme = build_theme(font, variant, tighten_spacing=True)
                if not plan_fits(plan, theme):
                    overflow_attempts += 1
                    overflow_resampled = True
                    last_row = ManifestRow(
                        doc_id=doc_id,
                        source_type=source_type,
                        template_id=template.template_id,
                        font_family=variant.font_family,
                        layout_variant=variant.layout_variant,
                        has_header=variant.has_header,
                        has_footer=variant.has_footer,
                        has_small_text=variant.has_small_text,
                        page_size=variant.page_size,
                        margin_preset=variant.margin_preset,
                        density_preset=variant.density_preset,
                        column_mode=variant.column_mode,
                        has_table_region=variant.has_table_region,
                        seed=config.seed,
                        pdf_path=None,
                        page_count=0,
                        status="rejected",
                        created_at=datetime.now(timezone.utc).isoformat(),
                        template_family=template.template_family,
                        generation_attempts=attempt,
                        overflow_resampled=True,
                        notes={"reason": "overflow"},
                        content_fingerprint=plan.content_fingerprint,
                    )
                    if overflow_attempts >= MAX_OVERFLOW_ATTEMPTS:
                        break
                    continue

            render_pdf(destination, plan, page_size, theme)
            row = ManifestRow(
                doc_id=doc_id,
                source_type=source_type,
                template_id=template.template_id,
                font_family=variant.font_family,
                layout_variant=variant.layout_variant,
                has_header=variant.has_header,
                has_footer=variant.has_footer,
                has_small_text=variant.has_small_text,
                page_size=variant.page_size,
                margin_preset=variant.margin_preset,
                density_preset=variant.density_preset,
                column_mode=variant.column_mode,
                has_table_region=variant.has_table_region,
                seed=config.seed,
                pdf_path=destination,
                page_count=1,
                status="generated",
                created_at=datetime.now(timezone.utc).isoformat(),
                template_family=template.template_family,
                generation_attempts=attempt,
                overflow_resampled=overflow_resampled,
                notes=None,
                content_fingerprint=plan.content_fingerprint,
            )
            validation = validate_generated_pdf(destination, row.to_record())
            if validation.valid:
                row.page_count = validation.page_count
                success_row = row.to_record()
                seen_fingerprints.add(plan.content_fingerprint)
                break

            _remove_invalid_output(destination)
            last_row = ManifestRow(
                doc_id=doc_id,
                source_type=source_type,
                template_id=template.template_id,
                font_family=variant.font_family,
                layout_variant=variant.layout_variant,
                has_header=variant.has_header,
                has_footer=variant.has_footer,
                has_small_text=variant.has_small_text,
                page_size=variant.page_size,
                margin_preset=variant.margin_preset,
                density_preset=variant.density_preset,
                column_mode=variant.column_mode,
                has_table_region=variant.has_table_region,
                seed=config.seed,
                pdf_path=None,
                page_count=0,
                status="validation_failed",
                created_at=datetime.now(timezone.utc).isoformat(),
                template_family=template.template_family,
                generation_attempts=attempt,
                overflow_resampled=overflow_resampled,
                notes={"issues": validation.issues},
                content_fingerprint=plan.content_fingerprint,
            )

        final_row = success_row or (last_row.to_record() if last_row is not None else None)
        if final_row is None:
            raise RuntimeError(f"Failed to produce any manifest row for {doc_id}")
        append_manifest_row(config.manifest_path, final_row)
        generated_rows.append(final_row)
    return generated_rows
