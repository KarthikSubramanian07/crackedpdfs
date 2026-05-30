from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pdf_autogenerator.config import GeneratorConfig
from pdf_autogenerator.generator import generate_documents
from pdf_autogenerator.manifest import read_manifest
from pdf_autogenerator.validation import validate_manifest


def make_config(tmp_path: Path, **overrides) -> GeneratorConfig:
    base = GeneratorConfig(
        output_root=tmp_path / "out",
        total_count=6,
        seed=20260320,
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
    return replace(base, **overrides)


def test_rejected_overflow_rows_do_not_emit_pdf(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, total_count=1)

    def always_overflow(*args, **kwargs):
        return False

    monkeypatch.setattr("pdf_autogenerator.generator.plan_fits", always_overflow)
    rows = generate_documents(config)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "rejected"
    assert row["pdf_path"] is None


def test_generate_five_seeded_documents_per_family(tmp_path: Path) -> None:
    families = [
        "academic_handout",
        "business_memo_report",
        "form_worksheet",
        "policy_notice",
        "invoice_receipt",
        "syllabus_info",
    ]
    seed_offset = 0
    for family in families:
        config = make_config(
            tmp_path / family,
            total_count=5,
            seed=20260320 + seed_offset,
            family_weights={key: 1.0 if key == family else 0.0 for key in families},
        )
        rows = generate_documents(config)
        generated = [row for row in rows if row["status"] == "generated"]
        assert len(generated) == 5
        assert {row["source_type"] for row in generated} == {family}
        assert all(row["page_count"] == 1 for row in generated)
        seed_offset += 10


def test_mixed_hundred_document_run_spans_families_and_page_sizes(tmp_path: Path) -> None:
    config = make_config(tmp_path, total_count=100, seed=20260399)
    rows = generate_documents(config)
    generated = [row for row in rows if row["status"] == "generated"]
    assert generated
    assert len({row["source_type"] for row in generated}) == 6
    assert {row["page_size"] for row in generated} == {"letter", "a4"}
    assert any(row["has_footer"] for row in generated)
    assert any(not row["has_footer"] for row in generated)
    assert any(row["has_small_text"] for row in generated)
    assert any(not row["has_small_text"] for row in generated)
    valid, issues = validate_manifest(config.manifest_path)
    assert valid, issues


def test_resume_skips_existing_outputs_without_rewriting(tmp_path: Path) -> None:
    config = make_config(tmp_path, total_count=12, seed=20260401)
    rows = generate_documents(config)
    generated = [row for row in rows if row["status"] == "generated"]
    before = {row["doc_id"]: Path(row["pdf_path"]).stat().st_mtime for row in generated}
    manifest_before = read_manifest(config.manifest_path)
    rerun_rows = generate_documents(config)
    manifest_after = read_manifest(config.manifest_path)
    assert rerun_rows == []
    assert len(manifest_after) == len(manifest_before)
    for row in generated:
        assert Path(row["pdf_path"]).stat().st_mtime == before[row["doc_id"]]


def test_overwrite_replaces_manifest_instead_of_appending(tmp_path: Path) -> None:
    config = make_config(tmp_path, total_count=12, seed=20260402, resume_mode="overwrite")
    first_rows = generate_documents(config)
    second_rows = generate_documents(config)
    manifest_rows = read_manifest(config.manifest_path)
    assert len(first_rows) == 12
    assert len(second_rows) == 12
    assert len(manifest_rows) == 12
    assert len({row["doc_id"] for row in manifest_rows}) == 12
