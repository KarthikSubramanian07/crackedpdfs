from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pdf_autogenerator.audit import audit_dataset, find_near_duplicate_pairs
from pdf_autogenerator.audit_config import (
    AuditConfig,
    AuditExpectations,
    DistributionLimits,
    NearDuplicateConfig,
    SupportThresholds,
    load_audit_config,
)
from pdf_autogenerator.config import GeneratorConfig
from pdf_autogenerator.generator import generate_documents
from pdf_autogenerator.manifest import read_manifest
from pdf_autogenerator.templates import resolve_templates


def make_generation_config(tmp_path: Path, **overrides) -> GeneratorConfig:
    base = GeneratorConfig(
        output_root=tmp_path / "out",
        total_count=12,
        seed=20260325,
        resume_mode="overwrite",
        family_weights={
            "academic_handout": 1.0,
            "business_memo_report": 1.0,
            "form_worksheet": 1.0,
            "policy_notice": 1.0,
            "invoice_receipt": 1.0,
            "syllabus_info": 1.0,
        },
        template_allowlist=[],
        page_size_weights={"letter": 1.0, "a4": 1.0},
        margin_presets=["0.5in", "0.75in", "1.0in"],
        density_presets=["sparse", "normal", "dense"],
        font_allowlist=[
            "source_serif_4",
            "source_sans_3",
            "libre_baskerville",
            "liberation_serif",
            "liberation_sans",
        ],
        header_probability=0.72,
        footer_probability=0.56,
        small_text_probability=0.34,
        table_region_probability=0.8,
    )
    values = base.__dict__ | overrides
    return GeneratorConfig(**values)


def make_audit_config(generation_config: GeneratorConfig, **overrides) -> AuditConfig:
    expected_templates = [
        template
        for template in resolve_templates(generation_config.template_allowlist)
        if generation_config.family_weights.get(template.source_type, 0) > 0
    ]
    base = AuditConfig(
        profile="benign_only",
        config_path=(generation_config.output_root / "audit.yaml"),
        stage_field="stage",
        default_stage="benign",
        allow_missing_stage_for_default=True,
        allowed_stages=("benign",),
        allowed_statuses=("generated",),
        regime_field="regime",
        parent_field="parent_doc_id",
        allowed_regimes=tuple(),
        required_common_fields=("doc_id", "status", "pdf_path", "page_count"),
        required_stage_fields={
            "benign": (
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
            ),
            "injected": (
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
                "parent_doc_id",
                "regime",
            ),
        },
        expectations=AuditExpectations(
            families=tuple(sorted({template.source_type for template in expected_templates})),
            templates=tuple(sorted(template.template_id for template in expected_templates)),
            fonts=("Source Serif 4", "Source Sans 3", "Libre Baskerville", "Liberation Serif", "Liberation Sans"),
            page_sizes=("a4", "letter"),
            margin_presets=("0.5in", "0.75in", "1.0in"),
            density_presets=("dense", "normal", "sparse"),
        ),
        support_thresholds=SupportThresholds(
            min_family_count=1,
            min_template_count=1,
            min_regime_count=1,
        ),
        distribution_limits=DistributionLimits(
            max_family_share=1.0,
            max_template_share=1.0,
            max_regime_share=1.0,
        ),
        near_duplicate=NearDuplicateConfig(
            similarity_threshold=0.98,
            shingle_size=4,
            band_count=4,
            rows_per_band=3,
            max_bucket_size=100,
            sample_limit=10,
        ),
        suspicious_keywords=(
            "ignore previous",
            "system prompt",
            "prompt injection",
            "developer message",
        ),
    )
    values = base.__dict__ | overrides
    return AuditConfig(**values)


def test_benign_only_audit_passes_on_generated_dataset(tmp_path: Path) -> None:
    generation_config = make_generation_config(tmp_path, total_count=24)
    generate_documents(generation_config)
    report = audit_dataset(generation_config.manifest_path, make_audit_config(generation_config))
    assert report["overall_pass"] is True
    assert report["checks"]["schema_validation"]["status"] == "pass"


def test_mixed_audit_validates_regimes_and_injected_metadata(tmp_path: Path) -> None:
    generation_config = make_generation_config(
        tmp_path,
        total_count=2,
        family_weights={
            "academic_handout": 0.0,
            "business_memo_report": 1.0,
            "form_worksheet": 0.0,
            "policy_notice": 0.0,
            "invoice_receipt": 1.0,
            "syllabus_info": 0.0,
        },
        template_allowlist=["executive-memo", "invoice"],
        page_size_weights={"letter": 1.0},
        margin_presets=["0.75in"],
        density_presets=["normal"],
        font_allowlist=["source_serif_4"],
    )
    generate_documents(generation_config)
    rows = read_manifest(generation_config.manifest_path)
    rows[0]["stage"] = "benign"
    rows[1]["stage"] = "injected"
    rows[1]["parent_doc_id"] = rows[0]["doc_id"]
    rows[1]["regime"] = "overlay"
    mixed_manifest = tmp_path / "mixed_manifest.jsonl"
    with mixed_manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")

    mixed_audit_config = make_audit_config(
        generation_config,
        profile="mixed",
        allow_missing_stage_for_default=False,
        allowed_stages=("benign", "injected"),
        allowed_regimes=("overlay",),
        support_thresholds=SupportThresholds(min_family_count=1, min_template_count=1, min_regime_count=1),
    )
    passing_report = audit_dataset(mixed_manifest, mixed_audit_config)
    assert passing_report["overall_pass"] is True

    rows[1].pop("regime")
    broken_manifest = tmp_path / "mixed_manifest_broken.jsonl"
    with broken_manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")
    failing_report = audit_dataset(broken_manifest, mixed_audit_config)
    assert failing_report["overall_pass"] is False
    assert failing_report["checks"]["injected_metadata_check"]["status"] == "fail"


def test_load_audit_config_derives_expectations_from_generator_config(tmp_path: Path) -> None:
    generator_yaml = tmp_path / "generator.yaml"
    generator_yaml.write_text(
        "\n".join(
            [
                f"output_root: {str((tmp_path / 'out')).replace(chr(92), '/')}",
                "total_count: 24",
                "seed: 20260325",
                "resume_mode: overwrite",
                "family_weights:",
                "  academic_handout: 1.0",
                "  business_memo_report: 1.0",
                "  form_worksheet: 0.0",
                "  policy_notice: 0.0",
                "  invoice_receipt: 0.0",
                "  syllabus_info: 0.0",
                "template_allowlist:",
                "  - lecture-handout",
                "  - executive-memo",
                "page_size_weights:",
                "  letter: 1.0",
                "margin_presets:",
                "  - 0.75in",
                "density_presets:",
                "  - normal",
                "font_allowlist:",
                "  - source_serif_4",
                "header_probability: 0.72",
                "footer_probability: 0.56",
                "small_text_probability: 0.34",
                "table_region_probability: 0.8",
            ]
        ),
        encoding="utf-8",
    )
    audit_yaml = tmp_path / "audit.yaml"
    audit_yaml.write_text(
        "\n".join(
            [
                "profile: benign_only",
                f"generator_config_path: {generator_yaml.name}",
                "support_thresholds:",
                "  min_family_count: 1",
                "  min_template_count: 1",
                "  min_regime_count: 1",
                "distribution_limits:",
                "  max_family_share: 1.0",
                "  max_template_share: 1.0",
                "  max_regime_share: 1.0",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_audit_config(audit_yaml)
    assert loaded.expectations.families == ("academic_handout", "business_memo_report")
    assert loaded.expectations.templates == ("executive-memo", "lecture-handout")


def test_find_near_duplicate_pairs_uses_candidate_bucketing(tmp_path: Path) -> None:
    texts = {
        "doc-a": "Quarterly update operations summary staffing note project timeline review " * 4,
        "doc-b": "Quarterly update operations summary staffing note project timeline review schedule " * 4,
        "doc-c": "Course logistics office hours reading discussion practice worksheet prompt " * 4,
    }
    pairs, debug = find_near_duplicate_pairs(
        texts,
        similarity_threshold=0.75,
        shingle_size=3,
        band_count=4,
        rows_per_band=3,
        max_bucket_size=20,
        sample_limit=10,
    )
    pair_ids = {(pair["doc_id_a"], pair["doc_id_b"]) for pair in pairs}
    assert ("doc-a", "doc-b") in pair_ids or ("doc-b", "doc-a") in pair_ids
    assert debug["candidate_pair_count"] < 3
