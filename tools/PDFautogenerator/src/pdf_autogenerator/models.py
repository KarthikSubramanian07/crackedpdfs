from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from reportlab.lib.pagesizes import A4, letter


KNOWN_SOURCE_TYPES = (
    "academic_handout",
    "business_memo_report",
    "form_worksheet",
    "policy_notice",
    "invoice_receipt",
    "syllabus_info",
)

PAGE_SIZE_POINTS = {
    "letter": letter,
    "a4": A4,
}

MARGIN_PRESETS = {
    "0.5in": 36.0,
    "0.75in": 54.0,
    "1.0in": 72.0,
}


@dataclass(frozen=True)
class DensityProfile:
    title_size: float
    heading_size: float
    body_size: float
    small_size: float
    leading: float
    block_gap: float
    section_gap: float
    content_level: int


DENSITY_PROFILES = {
    "sparse": DensityProfile(
        title_size=18.0,
        heading_size=13.5,
        body_size=11.5,
        small_size=8.0,
        leading=14.5,
        block_gap=8.0,
        section_gap=12.0,
        content_level=0,
    ),
    "normal": DensityProfile(
        title_size=16.0,
        heading_size=13.0,
        body_size=10.5,
        small_size=7.5,
        leading=13.0,
        block_gap=7.0,
        section_gap=10.0,
        content_level=1,
    ),
    "dense": DensityProfile(
        title_size=14.0,
        heading_size=12.0,
        body_size=9.5,
        small_size=7.0,
        leading=11.5,
        block_gap=5.0,
        section_gap=8.0,
        content_level=2,
    ),
}


@dataclass(frozen=True)
class VariantChoices:
    page_size: str
    margin_preset: str
    density_preset: str
    font_key: str
    font_family: str
    has_header: bool
    has_footer: bool
    has_small_text: bool
    column_mode: str
    has_table_region: bool

    @property
    def layout_variant(self) -> str:
        flags = [
            self.column_mode,
            self.density_preset,
            "header" if self.has_header else "no-header",
            "footer" if self.has_footer else "no-footer",
            "small" if self.has_small_text else "standard",
            "table" if self.has_table_region else "plain",
        ]
        return "_".join(flags)


@dataclass(frozen=True)
class RegionSpec:
    name: str
    x: float
    y: float
    width: float
    height: float
    padding: float = 6.0
    border: bool = False
    background_color: str | None = None

    @property
    def usable_width(self) -> float:
        return max(self.width - (2 * self.padding), 1.0)

    @property
    def usable_height(self) -> float:
        return max(self.height - (2 * self.padding), 1.0)


@dataclass
class BlockSpec:
    kind: str
    text: str | None = None
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    align: str = "left"
    bold: bool = False
    small: bool = False
    boxed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegionPlan:
    spec: RegionSpec
    blocks: list[BlockSpec] = field(default_factory=list)


@dataclass
class DocumentPlan:
    template_id: str
    source_type: str
    template_family: str
    title: str
    regions: list[RegionPlan]
    content_fingerprint: str


GeometryBuilder = Callable[[VariantChoices, tuple[float, float]], dict[str, RegionSpec]]
Composer = Callable[[Any, VariantChoices, dict[str, Any], "TemplateDefinition"], dict[str, list[BlockSpec]]]


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    source_type: str
    template_family: str
    display_name: str
    allows_two_columns: bool = False
    supports_table_region: bool = False
    requires_table_region: bool = False
    requires_header: bool = False
    geometry_builder: GeometryBuilder | None = None
    composer: Composer | None = None

    def supports_column_mode(self, column_mode: str) -> bool:
        return column_mode == "single" or self.allows_two_columns

    def legal_variant_count(self) -> int:
        column_options = 2 if self.allows_two_columns else 1
        header_options = 1 if self.requires_header else 2
        table_options = 1
        if self.supports_table_region and not self.requires_table_region:
            table_options = 2
        density_options = 3
        page_options = 2
        footer_options = 2
        small_text_options = 2
        return (
            column_options
            * header_options
            * table_options
            * density_options
            * page_options
            * footer_options
            * small_text_options
        )


@dataclass(frozen=True)
class FontDefinition:
    key: str
    display_name: str
    regular_file: str
    bold_file: str


@dataclass(frozen=True)
class RegisteredFontFamily:
    key: str
    display_name: str
    regular_name: str
    bold_name: str


@dataclass
class ManifestRow:
    doc_id: str
    source_type: str
    template_id: str
    font_family: str
    layout_variant: str
    has_header: bool
    has_footer: bool
    has_small_text: bool
    page_size: str
    margin_preset: str
    density_preset: str
    column_mode: str
    has_table_region: bool
    seed: int
    pdf_path: Path | None
    page_count: int
    status: str
    created_at: str
    template_family: str | None = None
    generation_attempts: int | None = None
    overflow_resampled: bool | None = None
    notes: dict[str, Any] | str | None = None
    content_fingerprint: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_type": self.source_type,
            "template_id": self.template_id,
            "font_family": self.font_family,
            "layout_variant": self.layout_variant,
            "has_header": self.has_header,
            "has_footer": self.has_footer,
            "has_small_text": self.has_small_text,
            "page_size": self.page_size,
            "margin_preset": self.margin_preset,
            "density_preset": self.density_preset,
            "column_mode": self.column_mode,
            "has_table_region": self.has_table_region,
            "seed": self.seed,
            "pdf_path": str(self.pdf_path) if self.pdf_path else None,
            "page_count": self.page_count,
            "status": self.status,
            "created_at": self.created_at,
            "template_family": self.template_family,
            "generation_attempts": self.generation_attempts,
            "overflow_resampled": self.overflow_resampled,
            "notes": self.notes,
            "content_fingerprint": self.content_fingerprint,
        }
