from __future__ import annotations

import json
from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from crackedpdfs_audit.cli import main
from crackedpdfs_audit.contracts import contract_satisfied, lexical_oracle_hits
from crackedpdfs_audit.corpus import build_tasks, run_audit, summarize_records, write_outputs
from crackedpdfs_audit.geometry import added_glyphs, extract_glyphs, summarize_glyphs, visibility_reasons
from crackedpdfs_audit.render import pixel_diff, reveal

BASE_STREAM = b"BT /F1 12 Tf 72 700 Td (Benign body text) Tj ET"


def write_pdf(path: Path, extra: bytes = b"", size=(612, 792), cropbox=None) -> Path:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=size)
    page = pdf.pages[0]
    page.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
            )
        )
    )
    page.Contents = pikepdf.Stream(pdf, BASE_STREAM + b"\n" + extra)
    if cropbox:
        page.CropBox = pikepdf.Array(cropbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(path)
    return path


def text_block(x: float, y: float, text: str, size: float = 12, mode: int = 0, rgb=(0, 0, 0)) -> bytes:
    r, g, b = rgb
    return f"q {mode} Tr {r} {g} {b} rg BT /F1 {size} Tf {x} {y} Td ({text}) Tj ET Q".encode()


@pytest.fixture()
def base_pdf(tmp_path: Path) -> Path:
    return write_pdf(tmp_path / "base.pdf")


def added(tmp_path: Path, base_pdf: Path, extra: bytes, **kwargs):
    candidate = write_pdf(tmp_path / "candidate.pdf", extra, **kwargs)
    page = extract_glyphs(candidate)[0]
    reference = extract_glyphs(base_pdf)[0]
    return candidate, page, added_glyphs(page, reference)


def test_reference_diff_isolates_only_added_text(tmp_path, base_pdf):
    _, page, glyphs = added(tmp_path, base_pdf, text_block(100, 400, "HIDDEN", mode=3))
    assert len(page.glyphs) == len("Benign body text") + len("HIDDEN")
    assert "".join(g.text for g in glyphs) == "HIDDEN"


def test_off_page_text_below_the_page_is_measured(tmp_path, base_pdf):
    # The paper v1 failure: regime anchors used as absolute points.
    extra = text_block(0.12, 0.78, "FIRST") + b"\n" + text_block(0.12, -13.62, "SECOND")
    _, page, glyphs = added(tmp_path, base_pdf, extra)
    summary = summarize_glyphs(glyphs, page.page_box)
    assert summary.clipped == len("FIRST")
    assert summary.below_page == len("SECOND")
    assert summary.realized_spatial_class == "straddles_page_edge"
    assert contract_satisfied("inside_page", glyphs, page.page_box) is False


def test_visibility_reasons_cover_each_hiding_mechanism(tmp_path, base_pdf):
    cases = {
        "invisible_render_mode": text_block(100, 400, "A", mode=3),
        "tiny_font": text_block(100, 400, "A", size=1.2),
        "low_contrast_fill": text_block(100, 400, "A", rgb=(0.96, 0.96, 0.96)),
        "off_page": text_block(10000, 10000, "A"),
    }
    for reason, extra in cases.items():
        _, page, glyphs = added(tmp_path, base_pdf, extra)
        assert len(glyphs) == 1
        assert reason in visibility_reasons(glyphs[0], page.page_box), reason

    _, page, glyphs = added(tmp_path, base_pdf, text_block(100, 400, "A"))
    assert visibility_reasons(glyphs[0], page.page_box) == []


def test_label_contracts(tmp_path, base_pdf):
    _, page, inside = added(tmp_path, base_pdf, text_block(200, 400, "INSIDE", mode=3))
    assert contract_satisfied("inside_page", inside, page.page_box)
    assert not contract_satisfied("extreme_off_page", inside, page.page_box)
    assert not contract_satisfied("near_margin", inside, page.page_box)

    _, page, off = added(tmp_path, base_pdf, text_block(-612, -792, "NEGATIVE"))
    assert contract_satisfied("negative_off_page", off, page.page_box)

    _, page, margin = added(tmp_path, base_pdf, text_block(24, 16, "FOOTER", size=1.2))
    assert contract_satisfied("near_margin", margin, page.page_box)
    assert contract_satisfied("unknown_label", margin, page.page_box) is None


def test_cropbox_defines_the_visible_page(tmp_path, base_pdf):
    _, page, glyphs = added(tmp_path, base_pdf, text_block(40, 400, "CROPPED"), cropbox=[100, 100, 500, 700])
    assert page.page_box == (100.0, 100.0, 500.0, 700.0)
    assert summarize_glyphs(glyphs, page.page_box).outside == len("CROPPED")


def test_lexical_oracle_tokens():
    assert lexical_oracle_hits("[DATASET_SAMPLE_ID=sample_1][MESSAGE_TYPE=x]") == [
        "DATASET_SAMPLE_ID",
        "MESSAGE_TYPE=",
    ]
    assert lexical_oracle_hits("ordinary text") == []


def test_pixel_diff_separates_rendered_from_unrendered_additions(tmp_path, base_pdf):
    off_page = write_pdf(tmp_path / "off.pdf", text_block(10000, 10000, "HIDDEN TEXT"))
    visible = write_pdf(tmp_path / "visible.pdf", text_block(100, 400, "VISIBLE TEXT"))
    assert pixel_diff(off_page, base_pdf).changed_pixels == 0
    assert pixel_diff(visible, base_pdf).changed_pixels > 50


def test_reveal_draws_off_page_text_on_an_expanded_canvas(tmp_path, base_pdf):
    candidate, page, glyphs = added(tmp_path, base_pdf, text_block(72, -200, "BELOW THE PAGE"))
    output = reveal(candidate, glyphs, page.page_box, tmp_path / "reveal.png", max_side_px=800)
    image = Image.open(output)
    assert image.size[1] > image.size[0]
    # The expanded canvas is taller than the page aspect ratio alone would give.
    assert image.size[1] / image.size[0] > 792 / 612


def test_corpus_audit_end_to_end(tmp_path):
    root = tmp_path / "corpus"
    write_pdf(root / "benign/s1.benign.pdf")
    write_pdf(
        root / "benign/s1.benign-confounder.pdf",
        text_block(0.12, -13.62, "[DATASET_SAMPLE_ID=s1] note", mode=3),
    )
    write_pdf(
        root / "injected/s1.injected.pdf", text_block(0.12, -13.62, "[DATASET_SAMPLE_ID=s1] attack", mode=3)
    )
    write_pdf(root / "benign/s2.benign.pdf")
    write_pdf(root / "benign/s2.benign-confounder.pdf", text_block(10000, 10000, "note"))
    write_pdf(root / "injected/s2.injected.pdf", text_block(10000, 10000, "attack"))
    rows = []
    for sample, label in (("s1", "inside_page"), ("s2", "extreme_off_page")):
        shared = {
            "sample_id": sample,
            "target_attack_family": "in_page_invisible_text",
            "target_physical_attack_strength": "weak",
            "target_physical_spatial_regime": label,
            "target_physical_rendering_regime": "invisible_render_mode",
            "confounder_physical_attack_strength": "weak",
            "confounder_physical_spatial_regime": label,
            "confounder_physical_rendering_regime": "invisible_render_mode",
        }
        rows += [
            {
                **shared,
                "pdf_id": f"{sample}.benign",
                "pdf_role": "benign_original",
                "file_path": f"benign/{sample}.benign.pdf",
            },
            {
                **shared,
                "pdf_id": f"{sample}.benign_confounder",
                "pdf_role": "benign_confounder",
                "file_path": f"benign/{sample}.benign-confounder.pdf",
            },
            {
                **shared,
                "pdf_id": f"{sample}.injected",
                "pdf_role": "injected_attack",
                "file_path": f"injected/{sample}.injected.pdf",
                "spatial_regime": label,
            },
        ]
    metadata = tmp_path / "metadata.jsonl"
    metadata.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    tasks = build_tasks(rows, root, render=True)
    assert len(tasks) == 4
    records = list(run_audit(tasks, workers=1))
    assert all(record["error"] is None for record in records)
    by_id = {record["pdf_id"]: record for record in records}
    assert by_id["s1.injected"]["contract_satisfied"] is False
    assert by_id["s1.injected"]["added_below_page"] == len("[DATASET_SAMPLE_ID=s1] attack")
    assert by_id["s1.injected"]["lexical_oracle_tokens"] == ["DATASET_SAMPLE_ID"]
    assert by_id["s2.injected"]["contract_satisfied"] is True
    assert by_id["s2.injected"]["changed_pixels_72dpi"] == 0

    summary = summarize_records(records)
    assert {(row["role"], row["spatial_label"]) for row in summary} == {
        ("benign_confounder", "extreme_off_page"),
        ("benign_confounder", "inside_page"),
        ("injected_attack", "extreme_off_page"),
        ("injected_attack", "inside_page"),
    }
    outputs = write_outputs(records, tmp_path / "out")
    assert (
        "| injected_attack | in_page_invisible_text | inside_page | 1 |"
        in outputs["summary_markdown"].read_text()
    )

    assert (
        main(
            [
                "corpus",
                "--root",
                str(root),
                "--metadata",
                str(metadata),
                "--out",
                str(tmp_path / "cli"),
                "--workers",
                "1",
            ]
        )
        == 0
    )
    assert (tmp_path / "cli" / "placement-audit-summary.csv").exists()


def test_file_command_json(tmp_path, base_pdf, capsys):
    candidate = write_pdf(tmp_path / "candidate.pdf", text_block(10000, 10000, "OFF"))
    assert (
        main(["file", str(candidate), "--reference", str(base_pdf), "--label", "extreme_off_page", "--json"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report[0]["outside"] == 3
    assert report[0]["contract_satisfied"] is True
