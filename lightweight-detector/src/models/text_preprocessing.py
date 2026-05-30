from __future__ import annotations

import re
from typing import Any


DEFAULT_BENCHMARK_WRAPPERS = [
    "SYSTEM_POLICY_DO_NOT_REMOVE",
    "BEGIN_SYSTEM_POLICY",
    "END_SYSTEM_POLICY",
    "BEGIN_SYSTEM_PROMPT",
    "END_SYSTEM_PROMPT",
    "BEGIN_PROMPT_INJECTION",
    "END_PROMPT_INJECTION",
    "DO_NOT_REMOVE",
    "dataset_sample_id",
    "message_type",
    "sample_id",
    "sample",
]

DEFAULT_SYNTHETIC_PHRASE_MARKERS = [
    "benign",
    "confounder",
    "document_layout_note",
    "document layout note",
    "layout note",
    "layout calibration",
    "layout calibration text",
    "calibration text only",
    "text only",
    "only text only",
    "contains no",
    "matched benign",
    "safe placeholder",
    "neutral placeholder",
    "training sample",
    "synthetic",
    "sentence records",
    "pagination and retention",
    "retention notice generated",
    "generated footer text",
    "footer text for layout",
    "control testing text",
    "screen reader parity",
    "hidden extraction layer",
    "archival sentence",
    "balanced sentence",
    "careful sentence",
    "detailed sentence",
    "editorial sentence",
    "formal sentence",
    "general sentence",
    "internal sentence",
    "local sentence",
    "neutral sentence",
    "ordinary sentence",
    "practical sentence",
    "routine sentence",
    "standard sentence",
    "technical sentence",
    "useful sentence",
    "verified sentence",
    "yearly sentence",
]


def build_text_preprocessing_config(text_cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = text_cfg or {}
    wrappers = cfg.get("known_benchmark_wrappers", DEFAULT_BENCHMARK_WRAPPERS)
    if not isinstance(wrappers, list):
        wrappers = DEFAULT_BENCHMARK_WRAPPERS
    synthetic_markers = cfg.get("synthetic_phrase_markers", DEFAULT_SYNTHETIC_PHRASE_MARKERS)
    if not isinstance(synthetic_markers, list):
        synthetic_markers = DEFAULT_SYNTHETIC_PHRASE_MARKERS
    return {
        "strip_known_benchmark_wrappers": bool(cfg.get("strip_known_benchmark_wrappers", False)),
        "known_benchmark_wrappers": [str(value) for value in wrappers if str(value).strip()],
        "strip_synthetic_phrase_markers": bool(cfg.get("strip_synthetic_phrase_markers", False)),
        "synthetic_phrase_markers": [
            str(value) for value in synthetic_markers if str(value).strip()
        ],
    }


def apply_text_preprocessing(text: str, preprocessing: dict[str, Any] | None) -> str:
    cfg = preprocessing or {}
    cleaned = _strip_known_scaffold_blocks(text)
    if not bool(cfg.get("strip_known_benchmark_wrappers", False)):
        cleaned = cleaned
    else:
        cleaned = re.sub(
            r"\[\s*(?:dataset_sample_id|message_type|sample_id)\s*=\s*[^\]]*\]",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        for field in ["dataset_sample_id", "message_type", "sample_id"]:
            cleaned = re.sub(
                r"\[\s*" + _spaced_token_pattern(field) + r"\s*=\s*[^\]]*\]",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
        for tag in cfg.get("known_benchmark_wrappers", DEFAULT_BENCHMARK_WRAPPERS):
            tag_text = str(tag).strip()
            if not tag_text:
                continue
            cleaned = re.sub(r"</?\s*" + re.escape(tag_text) + r"\s*>", " ", cleaned, flags=re.IGNORECASE)
            if len(_normalize_for_audit(tag_text)) >= 8:
                cleaned = re.sub(
                    r"<\s*/?\s*" + _spaced_token_pattern(tag_text) + r"\s*>",
                    " ",
                    cleaned,
                    flags=re.IGNORECASE,
                )
        for token in cfg.get("known_benchmark_wrappers", DEFAULT_BENCHMARK_WRAPPERS):
            token_text = str(token).strip()
            if not token_text:
                continue
            cleaned = re.sub(re.escape(token_text), " ", cleaned, flags=re.IGNORECASE)
            if len(_normalize_for_audit(token_text)) >= 8:
                cleaned = re.sub(_spaced_token_pattern(token_text), " ", cleaned, flags=re.IGNORECASE)

    if bool(cfg.get("strip_synthetic_phrase_markers", False)):
        cleaned = _strip_synthetic_generator_templates(cleaned)
        for marker in cfg.get("synthetic_phrase_markers", DEFAULT_SYNTHETIC_PHRASE_MARKERS):
            marker_text = str(marker).strip()
            if not marker_text:
                continue
            cleaned = re.sub(re.escape(marker_text), " ", cleaned, flags=re.IGNORECASE)
            if len(_normalize_for_audit(marker_text)) >= 5:
                cleaned = re.sub(_spaced_token_pattern(marker_text), " ", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(_loose_phrase_pattern(marker_text), " ", cleaned, flags=re.IGNORECASE)
        for field in ["document_layout_note", "benign_confounder_family", "pdf_role"]:
            cleaned = re.sub(
                r"\[\s*" + _spaced_token_pattern(field) + r"\s*=\s*[^\]]*\]",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
    cleaned = re.sub(r"<\s*>", " ", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def audit_text_feature_weights(
    pipeline: Any,
    *,
    known_wrappers: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    classifier = pipeline.named_steps["classifier"]
    features = pipeline.named_steps["features"]
    if not hasattr(classifier, "coef_") or not hasattr(features, "get_feature_names_out"):
        return {"top_positive": [], "top_negative": [], "wrapper_token_hits": []}

    names = features.get_feature_names_out()
    weights = classifier.coef_[0]
    positive = _rank_weights(names, weights, reverse=True, limit=limit)
    negative = _rank_weights(names, weights, reverse=False, limit=limit)
    wrapper_hits = _wrapper_hits([*positive, *negative], known_wrappers or DEFAULT_BENCHMARK_WRAPPERS)
    return {
        "top_positive": positive,
        "top_negative": negative,
        "wrapper_token_hits": wrapper_hits,
        "wrapper_token_hit_count": len(wrapper_hits),
    }


def _rank_weights(names: Any, weights: Any, *, reverse: bool, limit: int) -> list[dict[str, Any]]:
    indexed = sorted(
        enumerate(weights),
        key=lambda item: float(item[1]),
        reverse=reverse,
    )[:limit]
    return [
        {
            "feature": str(names[index]),
            "weight": float(weight),
            "abs_weight": abs(float(weight)),
            "rank": rank + 1,
        }
        for rank, (index, weight) in enumerate(indexed)
    ]


def _wrapper_hits(rows: list[dict[str, Any]], wrappers: list[str]) -> list[dict[str, Any]]:
    normalized_wrappers = {
        wrapper: _normalize_for_audit(wrapper)
        for wrapper in wrappers
        if _normalize_for_audit(wrapper)
    }
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        feature = str(row.get("feature", ""))
        normalized_feature = _normalize_for_audit(feature)
        if len(normalized_feature) < 4:
            continue
        for wrapper, normalized_wrapper in normalized_wrappers.items():
            matched = normalized_wrapper in normalized_feature
            if not matched:
                continue
            key = (feature, wrapper)
            if key in seen:
                continue
            seen.add(key)
            hits.append({**row, "matched_wrapper": wrapper})
    return hits


def _normalize_for_audit(value: str) -> str:
    value = re.sub(r"^(?:text__)?(?:word|char)__", "", value)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _spaced_token_pattern(token: str) -> str:
    normalized = _normalize_for_audit(token)
    return r"[\s_\-]*".join(re.escape(char) for char in normalized)


def _loose_phrase_pattern(phrase: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", phrase) if word]
    if not words:
        return re.escape(phrase)
    return r"\b" + r"[\W_]+".join(re.escape(word) for word in words) + r"\b"


def _strip_known_scaffold_blocks(text: str) -> str:
    cleaned = text or ""
    for tag in ["DOCUMENT_LAYOUT_NOTE"]:
        exact = re.escape(tag)
        cleaned = re.sub(
            r"<\s*" + exact + r"\s*>.*?<\s*/\s*" + exact + r"\s*>",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        spaced = _spaced_token_pattern(tag)
        cleaned = re.sub(
            r"<\s*" + spaced + r"\s*>.*?<\s*/\s*" + spaced + r"\s*>",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return cleaned


def _strip_synthetic_generator_templates(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(
        r"\b[a-z]{3,}\s+sentence\s+\d+(?:\s+records)?\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b[a-z]{3,}\s+sentence[\W_\d]+records\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:archival|balanced|careful|detailed|editorial|formal|general|internal|local|neutral|ordinary|practical|routine|standard|technical|useful|verified|yearly)\s+sentence\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned
