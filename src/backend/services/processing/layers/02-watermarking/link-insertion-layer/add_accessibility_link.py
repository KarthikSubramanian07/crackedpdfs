#!/usr/bin/env python3
"""
Accessibility link injector using PyPDF2 + ReportLab.

Draws a call-to-action on the final page and embeds a click-through link.
"""

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors

CTA_PADDING_X = 12
CTA_PADDING_Y = 6
CTA_MIN_WIDTH = 150
CTA_BOTTOM_MARGIN = 32
CTA_MARGIN_X = 28
ACCESSIBILITY_PARAM = "doc"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inject accessibility links into PDFs.")
    parser.add_argument("input_path", help="Absolute path to the source PDF.")
    parser.add_argument("output_path", help="Absolute path where the processed PDF should be written.")
    parser.add_argument("token", help="Access token used to build the accessibility URL.")
    parser.add_argument("--base-url", default="https://solvance.ai", help="Base URL for accessibility requests.")
    parser.add_argument("--position", choices=["bottom-left", "bottom-center", "bottom-right"], default="bottom-right")
    parser.add_argument("--font-size", type=int, default=10)
    parser.add_argument("--text", default="Request Accessible Copy")
    parser.add_argument("--reference-path", help="Pre-rasterization PDF for adaptive placement")
    return parser.parse_args()


def draw_overlay(
    width: float,
    height: float,
    text: str,
    font_size: int,
    x: float,
    y: float,
    box_width: float,
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    box_height = font_size + CTA_PADDING_Y * 2

    c.setFillColor(colors.HexColor("#0F172A"))
    c.roundRect(
        x - CTA_PADDING_X,
        y - CTA_PADDING_Y,
        box_width,
        box_height,
        6,
        fill=1,
        stroke=0,
    )

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(x, y, text)
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def compute_box_left(width: float, box_width: float, position: str) -> float:
    right_bound = max(CTA_MARGIN_X, width - box_width - CTA_MARGIN_X)
    if position == "bottom-left":
        return CTA_MARGIN_X
    if position == "bottom-center":
        centered = (width - box_width) / 2
        return min(max(centered, CTA_MARGIN_X), right_bound)
    return right_bound


def adjust_y_with_reference(reference_path: str | None, default_y: float, box_height: float) -> float:
    if not reference_path:
        return default_y
    try:
        import pdfplumber
    except ImportError:
        return default_y

    ref = Path(reference_path)
    if not ref.exists():
        return default_y

    try:
        with pdfplumber.open(str(ref)) as ref_pdf:
            if not ref_pdf.pages:
                return default_y
            page = ref_pdf.pages[-1]
            chars = page.chars
            if not chars:
                return default_y
            lowest = min(float(ch.get("y0", 0.0)) for ch in chars)
            clearance = max(lowest - box_height - 10, 20)
            return clearance
    except Exception:
        return default_y


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_path}")

    reader = PdfReader(str(input_path))
    if not reader.pages:
        raise ValueError("PDF has no pages")

    target_page = reader.pages[-1]
    width = float(target_page.mediabox.width)
    height = float(target_page.mediabox.height)

    link_url = f"{args.base_url.rstrip('/')}/accessibility/request?{ACCESSIBILITY_PARAM}={args.token}"
    text_width = pdfmetrics.stringWidth(args.text, "Helvetica-Bold", args.font_size)
    box_width = max(text_width + CTA_PADDING_X * 2, CTA_MIN_WIDTH)
    box_left = compute_box_left(width, box_width, args.position)
    box_height = args.font_size + CTA_PADDING_Y * 2
    baseline_y = CTA_BOTTOM_MARGIN + CTA_PADDING_Y
    baseline_y = adjust_y_with_reference(args.reference_path, baseline_y, box_height)

    overlay_pdf_bytes = draw_overlay(
        width,
        height,
        args.text,
        args.font_size,
        box_left + CTA_PADDING_X,
        baseline_y,
        box_width,
    )
    overlay_reader = PdfReader(BytesIO(overlay_pdf_bytes))
    overlay_page = overlay_reader.pages[0]
    target_page.merge_page(overlay_page)

    rect = RectangleObject(
        [
            box_left,
            baseline_y - CTA_PADDING_Y,
            box_left + box_width,
            baseline_y - CTA_PADDING_Y + box_height,
        ]
    )

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    target_page = writer.pages[-1]
    link_annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): rect,
            NameObject("/Border"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(0)]
            ),
            NameObject("/A"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject(link_url),
                }
            ),
        }
    )
    annotation_ref = writer._add_object(link_annotation)
    if "/Annots" in target_page:
        target_page["/Annots"].append(annotation_ref)
    else:
        target_page[NameObject("/Annots")] = ArrayObject([annotation_ref])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fp:
        writer.write(fp)

    print(json.dumps({
        "success": True,
        "output": str(output_path),
        "link": link_url,
        "position": args.position,
        "font_size": args.font_size
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - invoked via subprocess
        print(json.dumps({"success": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
