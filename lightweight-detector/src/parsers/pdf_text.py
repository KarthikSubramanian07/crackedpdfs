from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data.load_metadata import resolve_pdf_path


def extract_pypdf_text(file_path: str | Path, dataset_config: dict[str, Any]) -> str:
    """Extract visible PDF text through pypdf, avoiding raw PDF syntax and metadata."""
    from pypdf import PdfReader

    resolved = resolve_pdf_path(str(file_path), dataset_config)
    try:
        reader = PdfReader(str(resolved))
    except Exception:
        return ""

    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunk for chunk in chunks if chunk).strip()
