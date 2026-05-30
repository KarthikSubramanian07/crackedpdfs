from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pikepdf

from src.common import coerce_float, coerce_int, safe_divide
from src.features.schema import FEATURE_COLUMNS
from src.parsers.utils import (
    color_from_operands,
    get_page_dimensions,
    is_white_rgb,
    iter_page_streams,
    quadrant_for_point,
    safe_skewness,
    safe_variance,
    shannon_entropy,
    stream_length_bytes as get_stream_length_bytes,
    summarize_numeric,
)


TEXT_SHOW_OPS = {"Tj", "TJ", "'", '"'}
FILL_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}


@dataclass
class TextRecord:
    page: int
    x: float | None
    y: float | None
    page_width: float
    page_height: float
    font_size: float | None
    render_mode: int | None
    color: tuple[float, float, float] | None
    in_artifact: bool
    text_char_count: int


def extract_pdf_features(pdf_path: str | Path, extractor_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = extractor_config or {}
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF does not exist: {path}")

    box_name = str(config.get("page_box", "cropbox"))

    with pikepdf.open(str(path)) as pdf:
        page_widths: list[float] = []
        page_heights: list[float] = []
        page_stream_counts: list[int] = []
        page_nonwhite_fill: dict[int, bool] = {}
        records: list[TextRecord] = []
        parse_errors = 0
        artifact_bmc_count = 0
        artifact_emc_count = 0
        num_content_streams_total = 0
        num_text_show_ops = 0
        stream_lengths: list[int] = []

        for page_index, page in enumerate(pdf.pages):
            page_number = page_index + 1
            page_width, page_height = get_page_dimensions(page, box_name=box_name)
            page_widths.append(page_width)
            page_heights.append(page_height)
            page_nonwhite_fill[page_number] = False

            page_streams = iter_page_streams(page)
            stream_count = len(page_streams)
            page_stream_counts.append(stream_count)
            num_content_streams_total += stream_count

            state = {
                "x": 0.0,
                "y": 0.0,
                "font_size": None,
                "render_mode": None,
                "color": None,
                "leading": 0.0,
                "artifact_depth": 0,
            }

            for stream in page_streams:
                length_bytes = get_stream_length_bytes(stream)
                stream_lengths.append(length_bytes)
                try:
                    instructions = pikepdf.parse_content_stream(stream)
                except Exception:
                    parse_errors += 1
                    continue

                for instruction in instructions:
                    operator = str(instruction.operator)
                    operands = list(instruction.operands)

                    if operator == "BT":
                        state["x"] = 0.0
                        state["y"] = 0.0
                    elif operator == "Tf" and len(operands) >= 2:
                        state["font_size"] = coerce_float(operands[1])
                    elif operator == "Tr" and operands:
                        state["render_mode"] = coerce_int(operands[0])
                    elif operator in {"rg", "g"}:
                        color = color_from_operands(operator, operands)
                        if color is not None:
                            state["color"] = color
                    elif operator == "Td" and len(operands) >= 2:
                        dx = coerce_float(operands[0])
                        dy = coerce_float(operands[1])
                        if dx is not None:
                            state["x"] = float(state["x"]) + dx
                        if dy is not None:
                            state["y"] = float(state["y"]) + dy
                    elif operator == "TD" and len(operands) >= 2:
                        dx = coerce_float(operands[0])
                        dy = coerce_float(operands[1])
                        if dx is not None:
                            state["x"] = float(state["x"]) + dx
                        if dy is not None:
                            state["y"] = float(state["y"]) + dy
                            state["leading"] = -dy
                    elif operator == "Tm" and len(operands) >= 6:
                        x = coerce_float(operands[4])
                        y = coerce_float(operands[5])
                        if x is not None:
                            state["x"] = x
                        if y is not None:
                            state["y"] = y
                    elif operator == "TL" and operands:
                        leading = coerce_float(operands[0])
                        if leading is not None:
                            state["leading"] = leading
                    elif operator == "T*":
                        state["y"] = float(state["y"]) - float(state["leading"])
                    elif operator in {"BMC", "BDC"} and operands:
                        if str(operands[0]) == "/Artifact":
                            state["artifact_depth"] = int(state["artifact_depth"]) + 1
                            artifact_bmc_count += 1
                    elif operator == "EMC":
                        artifact_emc_count += 1
                        if int(state["artifact_depth"]) > 0:
                            state["artifact_depth"] = int(state["artifact_depth"]) - 1

                    if operator in FILL_OPS and not is_white_rgb(state["color"], float(config.get("white_color_threshold", 0.99))):
                        page_nonwhite_fill[page_number] = True

                    if operator in TEXT_SHOW_OPS:
                        if operator in {"'", '"'}:
                            state["y"] = float(state["y"]) - float(state["leading"])
                        text_char_count = _text_char_count(operator, operands)
                        num_text_show_ops += 1
                        records.append(
                            TextRecord(
                                page=page_number,
                                x=coerce_float(state["x"]),
                                y=coerce_float(state["y"]),
                                page_width=page_width,
                                page_height=page_height,
                                font_size=coerce_float(state["font_size"]),
                                render_mode=coerce_int(state["render_mode"]),
                                color=state["color"],
                                in_artifact=bool(state["artifact_depth"]),
                                text_char_count=text_char_count,
                            )
                        )

    features = _build_feature_payload(
        records=records,
        page_widths=page_widths,
        page_heights=page_heights,
        page_stream_counts=page_stream_counts,
        page_nonwhite_fill=page_nonwhite_fill,
        num_content_streams_total=num_content_streams_total,
        artifact_bmc_count=artifact_bmc_count,
        artifact_emc_count=artifact_emc_count,
        num_text_show_ops=num_text_show_ops,
        stream_lengths=stream_lengths,
        config=config,
        pdf_path=path,
    )

    return {
        "features": features,
        "parse_errors": parse_errors,
    }


def _build_feature_payload(
    *,
    records: list[TextRecord],
    page_widths: list[float],
    page_heights: list[float],
    page_stream_counts: list[int],
    page_nonwhite_fill: dict[int, bool],
    num_content_streams_total: int,
    artifact_bmc_count: int,
    artifact_emc_count: int,
    num_text_show_ops: int,
    stream_lengths: list[int],
    config: dict[str, Any],
    pdf_path: Path,
) -> dict[str, float | int]:
    white_threshold = float(config.get("white_color_threshold", 0.99))
    entropy_bins = int(config.get("text_entropy_bins", 10))
    coord_clip_min = float(config.get("coord_clip_min", -1.0))
    coord_clip_max = float(config.get("coord_clip_max", 2.0))
    small_font_threshold = float(config.get("small_font_threshold", 3.0))
    hidden_font_threshold = float(config.get("hidden_font_threshold", 2.0))
    bbox_char_width_factor = float(config.get("bbox_char_width_factor", 0.5))
    include_text_mismatch = bool(config.get("include_text_mismatch", False))

    positioned = [record for record in records if record.x is not None and record.y is not None]
    x_norm = [safe_divide(float(record.x), record.page_width) for record in positioned]
    y_norm = [safe_divide(float(record.y), record.page_height) for record in positioned]
    font_sizes = [float(record.font_size) for record in records if record.font_size is not None]

    outside_page = [
        record
        for record in positioned
        if float(record.x) < 0
        or float(record.y) < 0
        or float(record.x) > record.page_width
        or float(record.y) > record.page_height
    ]
    negative_coord = [
        record for record in positioned if float(record.x) < 0 or float(record.y) < 0
    ]
    render_mode_3 = [record for record in records if record.render_mode == 3]
    nonstandard_render_modes = [
        record for record in records if record.render_mode not in {None, 0, 3}
    ]
    white_text = [record for record in records if is_white_rgb(record.color, white_threshold)]

    distances: list[float] = []
    quadrant_counts = {"q1": 0, "q2": 0, "q3": 0, "q4": 0}
    bbox_areas: list[float] = []
    suspicious_x: list[float] = []
    suspicious_y: list[float] = []
    visible_char_estimate = 0

    for record in positioned:
        x = float(record.x)
        y = float(record.y)
        norm_x = safe_divide(x, record.page_width)
        norm_y = safe_divide(y, record.page_height)
        distance = math.sqrt((norm_x - 0.5) ** 2 + (norm_y - 0.5) ** 2)
        distances.append(distance)
        quadrant_counts[quadrant_for_point(x, y, record.page_width, record.page_height)] += 1
        bbox_areas.append(_estimated_bbox_area(record, bbox_char_width_factor))

        hidden = _infer_hidden(record, hidden_font_threshold, white_threshold)
        suspicious = hidden or record.in_artifact or (
            record.font_size is not None and float(record.font_size) < small_font_threshold
        )
        if suspicious:
            suspicious_x.append(norm_x)
            suspicious_y.append(norm_y)
        if not hidden:
            visible_char_estimate += max(0, int(record.text_char_count))

    page_width = _mean_or_zero(page_widths)
    page_height = _mean_or_zero(page_heights)
    num_pages = len(page_widths)
    total_page_area = sum(width * height for width, height in zip(page_widths, page_heights))

    min_font_size, max_font_size, mean_font_size, std_font_size = summarize_numeric(font_sizes)
    num_font_lt_1 = sum(1 for value in font_sizes if value < 1.0)
    num_font_lt_2 = sum(1 for value in font_sizes if value < 2.0)
    num_font_lt_3 = sum(1 for value in font_sizes if value < 3.0)

    bbox_area_mean, bbox_area_std = _mean_std(bbox_areas)
    mean_distance = _mean_or_zero(distances)

    white_text_pages = {record.page for record in white_text}
    white_text_on_white_bg_flag = int(
        any(not page_nonwhite_fill.get(page_number, False) for page_number in white_text_pages)
    )

    extractor_char_count = 0
    char_count_difference = 0
    char_mismatch_ratio = 0.0
    if include_text_mismatch:
        extractor_char_count = _extractor_char_count(pdf_path)
        char_count_difference = abs(extractor_char_count - visible_char_estimate)
        char_mismatch_ratio = safe_divide(
            char_count_difference,
            max(extractor_char_count, visible_char_estimate, 1),
        )

    payload = {
        "page_width": page_width,
        "page_height": page_height,
        "num_text_objects": len(records),
        "num_text_outside_page_bounds": len(outside_page),
        "frac_text_outside_page": safe_divide(len(outside_page), len(records)),
        "num_text_negative_coords": len(negative_coord),
        "max_abs_x": max((abs(value) for value in x_norm), default=0.0),
        "max_abs_y": max((abs(value) for value in y_norm), default=0.0),
        "max_distance_from_page_center": max(distances, default=0.0),
        "mean_distance_from_page_center": mean_distance,
        "coord_entropy_x": shannon_entropy(
            x_norm, bins=entropy_bins, clip_min=coord_clip_min, clip_max=coord_clip_max
        ),
        "coord_entropy_y": shannon_entropy(
            y_norm, bins=entropy_bins, clip_min=coord_clip_min, clip_max=coord_clip_max
        ),
        "bbox_area_mean": bbox_area_mean,
        "bbox_area_std": bbox_area_std,
        "quadrant_density_q1": safe_divide(quadrant_counts["q1"], len(positioned)),
        "quadrant_density_q2": safe_divide(quadrant_counts["q2"], len(positioned)),
        "quadrant_density_q3": safe_divide(quadrant_counts["q3"], len(positioned)),
        "quadrant_density_q4": safe_divide(quadrant_counts["q4"], len(positioned)),
        "min_font_size": min_font_size,
        "max_font_size": max_font_size,
        "mean_font_size": mean_font_size,
        "std_font_size": std_font_size,
        "num_font_lt_1": num_font_lt_1,
        "num_font_lt_2": num_font_lt_2,
        "num_font_lt_3": num_font_lt_3,
        "frac_small_font_objects": safe_divide(num_font_lt_3, len(records)),
        "font_size_skewness": safe_skewness(font_sizes),
        "num_render_mode_3": len(render_mode_3),
        "frac_render_mode_3": safe_divide(len(render_mode_3), len(records)),
        "num_nonstandard_render_modes": len(nonstandard_render_modes),
        "num_white_text": len(white_text),
        "frac_white_text": safe_divide(len(white_text), len(records)),
        "white_text_on_white_bg_flag": white_text_on_white_bg_flag,
        "num_pages": num_pages,
        "num_content_streams_total": num_content_streams_total,
        "mean_streams_per_page": _mean_or_zero(page_stream_counts),
        "std_streams_per_page": _std_or_zero(page_stream_counts),
        "artifact_bmc_count": artifact_bmc_count,
        "artifact_emc_count": artifact_emc_count,
        "has_artifact_wrapper": int(artifact_bmc_count > 0),
        "num_text_show_ops": num_text_show_ops,
        "num_stream_objects": len(stream_lengths),
        "avg_stream_length_bytes": _mean_or_zero(stream_lengths),
        "max_stream_length_bytes": max(stream_lengths, default=0),
        "extractor_char_count": extractor_char_count,
        "render_visible_char_estimate": visible_char_estimate,
        "char_count_difference": char_count_difference,
        "char_mismatch_ratio": char_mismatch_ratio,
        "text_density_per_page": safe_divide(sum(record.text_char_count for record in records), max(total_page_area, 1.0)),
        "injection_cluster_score": _cluster_score(suspicious_x, suspicious_y),
        "coord_variance_x": safe_variance(x_norm),
        "coord_variance_y": safe_variance(y_norm),
        "distance_outlier_score": _distance_outlier_score(distances),
    }

    missing = [column for column in FEATURE_COLUMNS if column not in payload]
    if missing:
        raise ValueError(f"Feature extractor did not emit required columns: {missing}")
    return payload


def _text_char_count(operator: str, operands: list[Any]) -> int:
    if not operands:
        return 0
    if operator == "TJ" and operands:
        sequence = operands[0]
        try:
            return sum(len(str(item)) for item in sequence if isinstance(item, pikepdf.String))
        except Exception:
            return 0
    if operator == '"' and len(operands) >= 3:
        return len(str(operands[2]))
    return len(str(operands[-1]))


def _infer_hidden(record: TextRecord, hidden_font_threshold: float, white_threshold: float) -> bool:
    if record.render_mode == 3:
        return True
    if record.x is not None and record.y is not None:
        if record.x < 0 or record.y < 0 or record.x > record.page_width or record.y > record.page_height:
            return True
    if record.font_size is not None and float(record.font_size) <= hidden_font_threshold:
        return True
    if is_white_rgb(record.color, white_threshold):
        return True
    return False


def _estimated_bbox_area(record: TextRecord, bbox_char_width_factor: float) -> float:
    if record.font_size is None or record.text_char_count <= 0:
        return 0.0
    page_area = max(record.page_width * record.page_height, 1.0)
    estimated_width = max(float(record.font_size) * bbox_char_width_factor * record.text_char_count, float(record.font_size))
    estimated_height = max(float(record.font_size), 1.0)
    return (estimated_width * estimated_height) / page_area


def _cluster_score(norm_x: list[float], norm_y: list[float]) -> float:
    if not norm_x or not norm_y:
        return 0.0
    if len(norm_x) == 1:
        return 1.0
    variance_sum = safe_variance(norm_x) + safe_variance(norm_y)
    return float(1.0 / (1.0 + 10.0 * variance_sum))


def _distance_outlier_score(distances: list[float]) -> float:
    if len(distances) < 2:
        return 0.0
    mean_distance = _mean_or_zero(distances)
    std_distance = _std_or_zero(distances)
    if std_distance == 0.0:
        return 0.0
    return max(abs((value - mean_distance) / std_distance) for value in distances)


def _extractor_char_count(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
    except Exception:
        return 0

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return 0

    total = 0
    for page in reader.pages:
        try:
            total += len(page.extract_text() or "")
        except Exception:
            continue
    return total


def _mean_or_zero(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _std_or_zero(values: list[float] | list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = _mean_or_zero(values)
    variance = sum((float(value) - mean_value) ** 2 for value in values) / len(values)
    return float(math.sqrt(variance))


def _mean_std(values: list[float]) -> tuple[float, float]:
    return _mean_or_zero(values), _std_or_zero(values)
