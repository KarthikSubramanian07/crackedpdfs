from __future__ import annotations

from pathlib import Path

from pdf_autogenerator.config import GeneratorConfig
from pdf_autogenerator.generator import generate_documents
from pdf_autogenerator.qa import QAThresholds, run_qa


def make_config(tmp_path: Path, **overrides) -> GeneratorConfig:
    config = GeneratorConfig(
        output_root=tmp_path / "out",
        total_count=24,
        seed=20260501,
        resume_mode="overwrite",
        family_weights={
            "academic_handout": 0.0,
            "business_memo_report": 1.0,
            "form_worksheet": 1.0,
            "policy_notice": 1.0,
            "invoice_receipt": 1.0,
            "syllabus_info": 0.0,
        },
        template_allowlist=[
            "executive-memo",
            "acknowledgement-form",
            "intake-worksheet",
            "checklist-form",
            "administrative-notice",
            "policy-bulletin",
            "invoice",
            "itemized-receipt",
        ],
        page_size_weights={"letter": 1.0},
        margin_presets=["0.75in"],
        density_presets=["normal"],
        font_allowlist=["source_serif_4"],
        header_probability=0.72,
        footer_probability=0.56,
        small_text_probability=0.34,
        table_region_probability=0.8,
    )
    values = config.__dict__ | overrides
    return GeneratorConfig(**values)


def test_profile_aware_qa_accepts_constrained_valid_config(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    generate_documents(config)
    report = run_qa(config.manifest_path, config=config)
    assert report["checks"]["family_coverage"]["status"] == "pass"
    assert report["checks"]["layout_diversity"]["status"] == "pass"
    assert report["checks"]["typography_diversity"]["status"] == "pass"


def test_qa_flags_near_duplicates_when_thresholds_require_it(tmp_path: Path) -> None:
    config = make_config(tmp_path, total_count=12)
    generate_documents(config)
    thresholds = QAThresholds(
        min_template_count=1,
        max_family_share=1.0,
        max_template_share=1.0,
        near_duplicate_threshold=0.0,
        repeated_line_share=1.0,
        min_nonwhite_ratio=0.0,
        max_nonwhite_ratio=1.0,
        min_char_count=0,
        max_char_count=10000,
    )
    report = run_qa(config.manifest_path, config=config, thresholds=thresholds)
    assert report["checks"]["content_realism"]["status"] == "fail"
    assert report["checks"]["content_realism"]["details"]["near_duplicates"]
