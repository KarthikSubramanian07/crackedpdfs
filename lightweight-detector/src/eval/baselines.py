from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.common import resolve_path
from src.data.load_metadata import load_dataset_config
from src.parsers.pdf_text import extract_pypdf_text


def run_rule_baseline(frame: pd.DataFrame) -> np.ndarray:
    """Deployable structural baseline over parsed PDF features only.

    This intentionally avoids generation-time regime metadata such as
    spatial_regime/rendering_regime. Those fields are useful for analysis, but
    using them would turn the baseline into an oracle.
    """
    scores = np.zeros(len(frame), dtype=float)

    def add_score(mask: pd.Series | np.ndarray, value: float) -> None:
        scores[np.asarray(mask, dtype=bool)] += value

    add_score(_numeric_series(frame, "num_text_outside_page_bounds") > 0, 0.20)
    add_score(_numeric_series(frame, "num_text_negative_coords") > 0, 0.15)
    add_score(_numeric_series(frame, "max_abs_x") > 2.0, 0.10)
    add_score(_numeric_series(frame, "max_abs_y") > 2.0, 0.10)
    add_score(_numeric_series(frame, "frac_render_mode_3") > 0.0, 0.15)
    add_score(_numeric_series(frame, "num_nonstandard_render_modes") > 0, 0.10)
    add_score(_numeric_series(frame, "num_white_text") > 0, 0.15)
    add_score(_numeric_series(frame, "min_font_size") < 3.0, 0.15)
    add_score(_numeric_series(frame, "frac_small_font_objects") > 0.0, 0.10)
    add_score(_numeric_series(frame, "has_artifact_wrapper") > 0, 0.10)
    add_score(_numeric_series(frame, "num_text_show_ops") >= 16, 0.10)

    return np.clip(scores, 0.0, 1.0)


def run_promptguard_baseline(
    frame: pd.DataFrame,
    *,
    dataset_config: dict[str, Any],
    model_name: str,
    max_length: int = 512,
    batch_size: int = 32,
    texts: list[str] | None = None,
) -> np.ndarray:
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception as exc:
        raise RuntimeError(
            "PromptGuard baseline requires transformers and torch to be installed."
        ) from exc

    hf_token = _resolve_hf_token()
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, token=hf_token)
    except Exception as exc:
        raise RuntimeError(_format_promptguard_load_error(model_name, exc)) from exc
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    positive_class_indices = _promptguard_positive_class_indices(model)

    if texts is None:
        texts = [extract_pdf_text(file_path, dataset_config) for file_path in frame["file_path"].astype(str).tolist()]
    if len(texts) != len(frame):
        raise ValueError(f"PromptGuard text count mismatch: {len(texts)} != {len(frame)}")
    scores: list[float] = []
    effective_batch_size = max(1, int(batch_size))
    total_batches = (len(texts) + effective_batch_size - 1) // effective_batch_size
    print(
        f"[promptguard] model={model_name} device={device} rows={len(texts)} "
        f"batch_size={effective_batch_size} batches={total_batches}",
        flush=True,
    )
    with torch.inference_mode():
        for batch_index, start in enumerate(range(0, len(texts), effective_batch_size), start=1):
            batch_texts = texts[start : start + effective_batch_size]
            encoded = tokenizer(
                [text or "" for text in batch_texts],
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=max_length,
            )
            encoded = {
                key: value.to(device) if hasattr(value, "to") else value
                for key, value in encoded.items()
            }
            logits = model(**encoded).logits
            if logits.shape[-1] == 1:
                batch_scores = torch.sigmoid(logits[:, 0]).detach().cpu().tolist()
            else:
                probabilities = torch.softmax(logits, dim=-1)
                batch_scores = probabilities[:, positive_class_indices].sum(dim=-1).detach().cpu().tolist()
            scores.extend(float(score) for score in batch_scores)
            if batch_index == 1 or batch_index == total_batches or batch_index % 10 == 0:
                print(f"[promptguard] batch {batch_index}/{total_batches}", flush=True)
    return np.asarray(scores, dtype=float)


def _promptguard_positive_class_indices(model: Any) -> list[int]:
    id2label = getattr(getattr(model, "config", None), "id2label", None) or {}
    label_by_index = {int(index): str(label).lower() for index, label in dict(id2label).items()}
    positive = [
        index
        for index, label in label_by_index.items()
        if "injection" in label or "jailbreak" in label
    ]
    if positive:
        return sorted(positive)
    label2id = getattr(getattr(model, "config", None), "label2id", None) or {}
    positive = [
        int(index)
        for label, index in dict(label2id).items()
        if "injection" in str(label).lower() or "jailbreak" in str(label).lower()
    ]
    if positive:
        return sorted(positive)
    # Fallback for binary classifiers where the last class is conventionally positive.
    num_labels = int(getattr(getattr(model, "config", None), "num_labels", 2) or 2)
    return [max(0, num_labels - 1)]


def extract_pdf_text(file_path: str, dataset_config: dict[str, Any]) -> str:
    return extract_pypdf_text(file_path, dataset_config)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame), dtype=float), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _resolve_hf_token() -> str | None:
    for env_name in ["HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"]:
        value = os.environ.get(env_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _format_promptguard_load_error(model_name: str, exc: Exception) -> str:
    message = str(exc)
    if "gated repo" in message.lower() or "401" in message.lower() or "access to model" in message.lower():
        return (
            f"PromptGuard baseline could not load '{model_name}'. "
            "This Meta model requires Hugging Face access. Run `hf auth login` with an approved account, "
            "or set `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` before evaluation."
        )
    return f"PromptGuard baseline could not load '{model_name}': {message}"
