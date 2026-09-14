"""Audit a CrackedPDFs-layout corpus: measured placement versus labels."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median

from .contracts import CONTRACTS, contract_satisfied, lexical_oracle_hits
from .geometry import PageGlyphs, added_glyphs, extract_glyphs, summarize_glyphs

AUDITED_ROLES = ("injected_attack", "benign_confounder")


@dataclass(frozen=True)
class AuditTask:
    pdf_id: str
    sample_id: str
    role: str
    family: str
    strength: str
    spatial_label: str
    rendering_label: str
    path: str
    reference_path: str | None
    render: bool


def read_metadata(path: str | Path) -> list[dict[str, object]]:
    path = Path(path)
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SystemExit(
                "Reading parquet needs pyarrow: pip install 'crackedpdfs-audit[parquet]'"
            ) from exc
        return pq.read_table(path).to_pylist()
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_tasks(
    rows: Iterable[dict[str, object]],
    root: str | Path,
    render: bool = False,
    families: set[str] | None = None,
) -> list[AuditTask]:
    root = Path(root)
    rows = list(rows)
    originals = {
        str(row["sample_id"]): str(row["file_path"])
        for row in rows
        if row.get("pdf_role") == "benign_original"
    }
    tasks: list[AuditTask] = []
    for row in rows:
        role = str(row.get("pdf_role"))
        if role not in AUDITED_ROLES:
            continue
        family = str(row.get("target_attack_family") or row.get("attack_family"))
        if families and family not in families:
            continue
        prefix = "target" if role == "injected_attack" else "confounder"
        path = root / str(row["file_path"])
        if not path.exists():
            continue
        reference = originals.get(str(row["sample_id"]))
        reference_path = root / reference if reference else None
        tasks.append(
            AuditTask(
                pdf_id=str(row["pdf_id"]),
                sample_id=str(row["sample_id"]),
                role=role,
                family=family,
                strength=str(row.get(f"{prefix}_physical_attack_strength") or row.get("attack_strength")),
                spatial_label=str(row.get(f"{prefix}_physical_spatial_regime") or row.get("spatial_regime")),
                rendering_label=str(
                    row.get(f"{prefix}_physical_rendering_regime") or row.get("rendering_regime")
                ),
                path=str(path),
                reference_path=str(reference_path) if reference_path and reference_path.exists() else None,
                render=render,
            )
        )
    return tasks


@lru_cache(maxsize=256)
def _cached_first_page(path: str) -> PageGlyphs | None:
    pages = extract_glyphs(path)
    return pages[0] if pages else None


def audit_task(task: AuditTask) -> dict[str, object]:
    record: dict[str, object] = {
        "pdf_id": task.pdf_id,
        "sample_id": task.sample_id,
        "role": task.role,
        "family": task.family,
        "strength": task.strength,
        "spatial_label": task.spatial_label,
        "rendering_label": task.rendering_label,
        "has_reference": task.reference_path is not None,
    }
    try:
        page = extract_glyphs(task.path)[0]
        reference = _cached_first_page(task.reference_path) if task.reference_path else None
        extra = added_glyphs(page, reference)
        summary = summarize_glyphs(extra, page.page_box)
        record.update({f"added_{key}": value for key, value in summary.as_dict().items()})
        record["page_box"] = list(page.page_box)
        record["contract_satisfied"] = contract_satisfied(task.spatial_label, extra, page.page_box)
        full_text = "".join(glyph.text for glyph in page.glyphs)
        record["lexical_oracle_tokens"] = lexical_oracle_hits(full_text)
        if task.render and task.reference_path:
            from .render import pixel_diff

            diff = pixel_diff(task.path, task.reference_path)
            record["changed_pixels_72dpi"] = diff.changed_pixels if diff else None
        record["error"] = None
    except Exception as exc:  # keep auditing the corpus; report the failure per file
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def run_audit(tasks: list[AuditTask], workers: int | None = None) -> Iterator[dict[str, object]]:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    if workers == 1:
        yield from map(audit_task, tasks)
        return
    # Sort by sample so each worker's reference cache stays warm.
    ordered = sorted(tasks, key=lambda task: task.sample_id)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(audit_task, ordered, chunksize=16)


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        if record.get("error"):
            continue
        groups[(str(record["role"]), str(record["family"]), str(record["spatial_label"]))].append(record)

    rows: list[dict[str, object]] = []
    for (role, family, label), items in sorted(groups.items()):
        glyphs = sum(int(item["added_glyphs"]) for item in items)
        realized: dict[str, int] = defaultdict(int)
        for item in items:
            realized[str(item["added_realized_spatial_class"])] += 1
        pixels = [
            int(item["changed_pixels_72dpi"])
            for item in items
            if item.get("changed_pixels_72dpi") is not None
        ]
        contract = [
            bool(item["contract_satisfied"]) for item in items if item.get("contract_satisfied") is not None
        ]
        rows.append(
            {
                "role": role,
                "family": family,
                "spatial_label": label,
                "pdfs": len(items),
                "mean_added_glyphs": round(glyphs / len(items), 1),
                "frac_glyphs_inside": round(sum(int(i["added_inside"]) for i in items) / glyphs, 4)
                if glyphs
                else None,
                "frac_glyphs_clipped": round(sum(int(i["added_clipped"]) for i in items) / glyphs, 4)
                if glyphs
                else None,
                "frac_glyphs_outside": round(sum(int(i["added_outside"]) for i in items) / glyphs, 4)
                if glyphs
                else None,
                "frac_glyphs_below_page": round(sum(int(i["added_below_page"]) for i in items) / glyphs, 4)
                if glyphs
                else None,
                "realized_classes": ";".join(f"{key}={value}" for key, value in sorted(realized.items())),
                "label_contract_rate": _rate(contract),
                "median_changed_pixels_72dpi": median(pixels) if pixels else None,
                "oracle_token_rate": _rate([bool(item["lexical_oracle_tokens"]) for item in items]),
            }
        )
    return rows


def write_outputs(records: list[dict[str, object]], out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records_path = out_dir / "placement-audit.jsonl"
    with records_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = summarize_records(records)
    summary_path = out_dir / "placement-audit-summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        if summary:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)

    markdown_path = out_dir / "placement-audit-summary.md"
    errors = sum(1 for record in records if record.get("error"))
    lines = [
        "# Placement audit",
        "",
        f"Audited PDFs: {len(records):,}. Extraction errors: {errors:,}.",
        "",
        "Label contracts:",
        "",
        *[f"- `{label}`: {text}." for label, text in CONTRACTS.items()],
        "",
        "| Role | Family | Label | PDFs | Mean added glyphs | Inside | Clipped | Outside | Below page | Label contract | Oracle tokens |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value: object) -> str:
        return "n/a" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))

    for row in summary:
        lines.append(
            f"| {row['role']} | {row['family']} | {row['spatial_label']} | {row['pdfs']:,} | "
            f"{row['mean_added_glyphs']:,} | {fmt(row['frac_glyphs_inside'])} | {fmt(row['frac_glyphs_clipped'])} | "
            f"{fmt(row['frac_glyphs_outside'])} | {fmt(row['frac_glyphs_below_page'])} | "
            f"{fmt(row['label_contract_rate'])} | {fmt(row['oracle_token_rate'])} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"records": records_path, "summary_csv": summary_path, "summary_markdown": markdown_path}
