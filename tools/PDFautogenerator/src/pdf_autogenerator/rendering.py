from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from .fonts import RegisteredFontFamily
from .models import DENSITY_PROFILES, BlockSpec, DocumentPlan, RegionPlan, VariantChoices


ALIGNMENTS = {
    "left": TA_LEFT,
    "center": TA_CENTER,
    "right": TA_RIGHT,
}


@dataclass(frozen=True)
class RenderTheme:
    regular_font: str
    bold_font: str
    title_size: float
    heading_size: float
    body_size: float
    small_size: float
    leading: float
    block_gap: float
    section_gap: float


def build_theme(font: RegisteredFontFamily, variant: VariantChoices, tighten_spacing: bool = False) -> RenderTheme:
    profile = DENSITY_PROFILES[variant.density_preset]
    block_gap = profile.block_gap - (1.0 if tighten_spacing else 0.0)
    section_gap = profile.section_gap - (2.0 if tighten_spacing else 0.0)
    leading = profile.leading - (0.5 if tighten_spacing else 0.0)
    return RenderTheme(
        regular_font=font.regular_name,
        bold_font=font.bold_name,
        title_size=profile.title_size,
        heading_size=profile.heading_size,
        body_size=profile.body_size,
        small_size=profile.small_size,
        leading=max(leading, profile.body_size + 1.0),
        block_gap=max(block_gap, 3.0),
        section_gap=max(section_gap, 4.0),
    )


def paragraph_style(
    theme: RenderTheme,
    role: str,
    *,
    bold: bool = False,
    align: str = "left",
    small: bool = False,
) -> ParagraphStyle:
    font_name = theme.bold_font if bold else theme.regular_font
    if role == "title":
        font_size = theme.title_size
        leading = theme.title_size + 2.0
    elif role == "section":
        font_size = theme.heading_size
        leading = theme.heading_size + 2.0
    elif small:
        font_size = theme.small_size
        leading = theme.small_size + 1.4
    else:
        font_size = theme.body_size
        leading = theme.leading
    return ParagraphStyle(
        name=f"{role}-{font_name}-{font_size}-{align}",
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        alignment=ALIGNMENTS[align],
        spaceAfter=0,
        textColor=colors.black,
    )


def _build_labeled_fields(block: BlockSpec, theme: RenderTheme, width: float) -> Table:
    row_multiplier = int(block.metadata.get("rows", 1))
    rows = [[Paragraph(escape(item), paragraph_style(theme, "body", bold=True)), ""] for item in block.items]
    col_widths = [max(width * 0.34, 90.0), max(width * 0.66, 140.0)]
    table = Table(rows, colWidths=col_widths, rowHeights=[18.0 * row_multiplier] * len(rows))
    style_commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(len(rows)):
        style_commands.append(("LINEBELOW", (1, row_index), (1, row_index), 0.4, colors.black))
    if block.boxed:
        style_commands.append(("BOX", (0, 0), (-1, -1), 0.6, colors.black))
    table.setStyle(TableStyle(style_commands))
    return table


def _build_signature_block(block: BlockSpec, theme: RenderTheme, width: float) -> Table:
    labels = block.items or ["Signature"]
    rows = [["", ""]]
    rows.append([Paragraph(escape(label), paragraph_style(theme, "body", small=True)) for label in labels[:2]])
    table = Table(rows, colWidths=[width / 2.0, width / 2.0], rowHeights=[20.0, 14.0])
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _build_table(block: BlockSpec, theme: RenderTheme, width: float) -> Table:
    header_style = paragraph_style(theme, "body", bold=True)
    body_style = paragraph_style(theme, "body", small=block.small)
    rows = [
        [Paragraph(escape(column), header_style) for column in block.columns],
        *[
            [Paragraph(escape(str(value)), body_style) for value in row]
            for row in block.rows
        ],
    ]
    column_count = max(len(block.columns), 1)
    col_width = width / column_count
    table = Table(rows, colWidths=[col_width] * column_count, repeatRows=1)
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if block.metadata.get("totals"):
        style_commands.append(("FONTNAME", (0, 1), (-1, -1), theme.bold_font))
    table.setStyle(TableStyle(style_commands))
    return table


def _build_checkbox_table(block: BlockSpec, theme: RenderTheme, width: float) -> Table:
    rows = [[u"\u25A1", Paragraph(escape(item), paragraph_style(theme, "body"))] for item in block.items]
    table = Table(rows, colWidths=[18.0, max(width - 18.0, 40.0)])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("FONTNAME", (0, 0), (0, -1), theme.regular_font),
                ("FONTSIZE", (0, 0), (0, -1), theme.body_size),
            ]
        )
    )
    return table


def block_to_flowables(block: BlockSpec, theme: RenderTheme, width: float) -> list:
    if block.kind == "title":
        return [
            Paragraph(
                escape(block.text or ""),
                paragraph_style(theme, "title", bold=block.bold, align=block.align),
            ),
            Spacer(1, theme.section_gap),
        ]
    if block.kind == "meta_line":
        return [
            Paragraph(
                escape(block.text or ""),
                paragraph_style(theme, "body", align=block.align, small=block.small),
            ),
            Spacer(1, theme.block_gap),
        ]
    if block.kind == "section_heading":
        return [
            Paragraph(
                escape(block.text or ""),
                paragraph_style(theme, "section", bold=block.bold, align=block.align),
            ),
            Spacer(1, theme.block_gap - 1.0),
        ]
    if block.kind in {"paragraph", "footer"}:
        return [
            Paragraph(
                escape(block.text or ""),
                paragraph_style(theme, "body", bold=block.bold, align=block.align, small=block.small),
            ),
            Spacer(1, theme.block_gap),
        ]
    if block.kind == "bullet_list":
        flowables: list = []
        for item in block.items:
            flowables.append(
                Paragraph(
                    f"&bull; {escape(item)}",
                    paragraph_style(theme, "body", small=block.small),
                )
            )
            flowables.append(Spacer(1, max(theme.block_gap - 2.0, 2.0)))
        if flowables and isinstance(flowables[-1], Spacer):
            flowables.pop()
        flowables.append(Spacer(1, theme.block_gap))
        return flowables
    if block.kind == "numbered_list":
        flowables = []
        for index, item in enumerate(block.items, start=1):
            flowables.append(
                Paragraph(
                    f"{index}. {escape(item)}",
                    paragraph_style(theme, "body", small=block.small),
                )
            )
            flowables.append(Spacer(1, max(theme.block_gap - 2.0, 2.0)))
        if flowables and isinstance(flowables[-1], Spacer):
            flowables.pop()
        flowables.append(Spacer(1, theme.block_gap))
        return flowables
    if block.kind == "checkbox_list":
        return [_build_checkbox_table(block, theme, width), Spacer(1, theme.block_gap)]
    if block.kind == "labeled_fields":
        return [_build_labeled_fields(block, theme, width), Spacer(1, theme.block_gap)]
    if block.kind == "signature_block":
        return [_build_signature_block(block, theme, width), Spacer(1, theme.block_gap)]
    if block.kind == "table":
        return [_build_table(block, theme, width), Spacer(1, theme.block_gap)]
    if block.kind == "rule":
        return [HRFlowable(width="100%", thickness=0.5, color=colors.black), Spacer(1, theme.block_gap)]
    return []


def build_region_flowables(region: RegionPlan, theme: RenderTheme) -> list:
    flowables: list = []
    for block in region.blocks:
        flowables.extend(block_to_flowables(block, theme, region.spec.usable_width))
    if flowables and isinstance(flowables[-1], Spacer):
        flowables.pop()
    return flowables


def measure_region(region: RegionPlan, theme: RenderTheme) -> float:
    height = 0.0
    for flowable in build_region_flowables(region, theme):
        _, wrapped_height = flowable.wrap(region.spec.usable_width, region.spec.usable_height)
        height += wrapped_height
    return height


def plan_fits(plan: DocumentPlan, theme: RenderTheme) -> bool:
    for region in plan.regions:
        height = measure_region(region, theme)
        if height > region.spec.usable_height + 0.5:
            return False
    return True


def render_pdf(
    destination: Path,
    plan: DocumentPlan,
    page_size: tuple[float, float],
    theme: RenderTheme,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(destination), pagesize=page_size, pageCompression=1)
    pdf.setTitle(plan.title)
    for region in plan.regions:
        if region.spec.background_color:
            pdf.setFillColor(colors.HexColor(region.spec.background_color))
            pdf.rect(region.spec.x, region.spec.y, region.spec.width, region.spec.height, fill=1, stroke=0)
            pdf.setFillColor(colors.black)
        if region.spec.border:
            pdf.rect(region.spec.x, region.spec.y, region.spec.width, region.spec.height, fill=0, stroke=1)
        flowables = build_region_flowables(region, theme)
        cursor_y = region.spec.y + region.spec.height - region.spec.padding
        draw_x = region.spec.x + region.spec.padding
        for flowable in flowables:
            _, height = flowable.wrap(region.spec.usable_width, region.spec.usable_height)
            cursor_y -= height
            flowable.drawOn(pdf, draw_x, cursor_y)
    pdf.showPage()
    pdf.save()
