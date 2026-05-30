from __future__ import annotations

import math
from typing import Any, Sequence

import pikepdf

from src.common import coerce_float, safe_mean, safe_std


def get_page_dimensions(page: pikepdf.Page, *, box_name: str = "cropbox") -> tuple[float, float]:
    candidate_boxes = _candidate_page_boxes(box_name)
    for candidate in candidate_boxes:
        dimensions = _read_box_dimensions(page, candidate)
        if dimensions is not None:
            width, height = dimensions
            rotation = _page_rotation(page)
            if rotation in {90, 270}:
                return height, width
            return width, height
    return 612.0, 792.0


def _candidate_page_boxes(box_name: str) -> list[str]:
    normalized = str(box_name).strip().lower()
    if normalized == "mediabox":
        return ["MediaBox", "CropBox"]
    return ["CropBox", "MediaBox"]


def _read_box_dimensions(page: pikepdf.Page, box_name: str) -> tuple[float, float] | None:
    try:
        box = getattr(page, box_name)
        width = float(box[2]) - float(box[0])
        height = float(box[3]) - float(box[1])
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    try:
        page_obj = page.obj
        box = page_obj.get(f"/{box_name}")
        if box is not None:
            width = float(box[2]) - float(box[0])
            height = float(box[3]) - float(box[1])
            if width > 0 and height > 0:
                return width, height
    except Exception:
        pass
    return None


def _page_rotation(page: pikepdf.Page) -> int:
    try:
        value = page.obj.get("/Rotate")
        if value is None:
            return 0
        return int(value) % 360
    except Exception:
        return 0


def iter_page_streams(page: pikepdf.Page) -> list[pikepdf.Object]:
    try:
        contents = page.obj.get("/Contents")
    except Exception:
        contents = None
    if contents is None:
        return []
    if isinstance(contents, pikepdf.Array):
        return list(contents)
    return [contents]


def stream_length_bytes(stream: pikepdf.Object) -> int:
    try:
        return len(stream.read_bytes())
    except Exception:
        return 0


def shannon_entropy(
    values: Sequence[float],
    *,
    bins: int = 10,
    clip_min: float = -1.0,
    clip_max: float = 2.0,
) -> float:
    if not values:
        return 0.0
    if clip_max <= clip_min:
        raise ValueError("clip_max must be greater than clip_min")

    histogram = [0] * bins
    span = clip_max - clip_min
    for value in values:
        clipped = max(clip_min, min(clip_max, value))
        ratio = (clipped - clip_min) / span
        index = min(bins - 1, max(0, int(ratio * bins)))
        histogram[index] += 1

    total = sum(histogram)
    if total == 0:
        return 0.0

    entropy = 0.0
    for count in histogram:
        if count == 0:
            continue
        probability = count / total
        entropy -= probability * math.log2(probability)
    return float(entropy)


def is_white_rgb(color: tuple[float, float, float] | None, threshold: float = 0.99) -> bool:
    if color is None:
        return False
    return all(channel >= threshold for channel in color)


def color_from_operands(operator: str, operands: Sequence[Any]) -> tuple[float, float, float] | None:
    if operator == "rg" and len(operands) >= 3:
        rgb = tuple(coerce_float(value) for value in operands[:3])
        if None not in rgb:
            return rgb  # type: ignore[return-value]
    if operator == "g" and operands:
        gray = coerce_float(operands[0])
        if gray is not None:
            return (gray, gray, gray)
    return None


def quadrant_for_point(x: float, y: float, page_w: float, page_h: float) -> str:
    half_w = page_w / 2.0
    half_h = page_h / 2.0
    if x >= half_w and y >= half_h:
        return "q1"
    if x < half_w and y >= half_h:
        return "q2"
    if x < half_w and y < half_h:
        return "q3"
    return "q4"


def summarize_numeric(values: Sequence[float]) -> tuple[float, float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0, 0.0
    return min(values), max(values), safe_mean(values), safe_std(values)


def safe_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = safe_mean(values)
    return float(sum((value - mean_value) ** 2 for value in values) / len(values))


def safe_skewness(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean_value = safe_mean(values)
    std_value = safe_std(values)
    if std_value == 0.0:
        return 0.0
    centered = [((value - mean_value) / std_value) ** 3 for value in values]
    return float(sum(centered) / len(centered))
