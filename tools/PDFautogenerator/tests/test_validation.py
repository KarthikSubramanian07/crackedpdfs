from __future__ import annotations

import json
from pathlib import Path

from pdf_autogenerator.config import GeneratorConfig
from pdf_autogenerator.generator import generate_documents
from pdf_autogenerator.manifest import append_manifest_row, read_manifest
from pdf_autogenerator.validation import validate_manifest


def make_config(tmp_path: Path) -> GeneratorConfig:
    return GeneratorConfig(
        output_root=tmp_path / "out",
        total_count=8,
        seed=20260420,
        resume_mode="skip",
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


def test_manifest_validation_accepts_generated_batch(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    generate_documents(config)
    valid, issues = validate_manifest(config.manifest_path)
    assert valid, issues


def test_manifest_validation_catches_duplicate_doc_ids_with_different_paths(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    rows = generate_documents(config)
    first = rows[0].copy()
    duplicate = dict(first)
    duplicate["pdf_path"] = str(tmp_path / "other.pdf")
    append_manifest_row(config.manifest_path, duplicate)
    valid, issues = validate_manifest(config.manifest_path)
    assert not valid
    assert any("duplicate_doc_id" in issue for issue in issues)


def test_manifest_validation_catches_duplicate_doc_ids_with_same_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    rows = generate_documents(config)
    append_manifest_row(config.manifest_path, dict(rows[0]))
    valid, issues = validate_manifest(config.manifest_path)
    assert not valid
    assert any("duplicate_doc_id" in issue for issue in issues)


def test_manifest_validation_catches_page_count_mismatch(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    generate_documents(config)
    rows = read_manifest(config.manifest_path)
    rows[0]["page_count"] = 999
    with config.manifest_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")
    valid, issues = validate_manifest(config.manifest_path)
    assert not valid
    assert any("page_count_mismatch" in issue for issue in issues)
