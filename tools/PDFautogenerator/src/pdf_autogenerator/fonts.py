from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import FontDefinition, RegisteredFontFamily


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

FONT_DEFINITIONS = {
    "source_serif_4": FontDefinition(
        key="source_serif_4",
        display_name="Source Serif 4",
        regular_file="source_serif_4/SourceSerif4-Regular.ttf",
        bold_file="source_serif_4/SourceSerif4-Bold.ttf",
    ),
    "source_sans_3": FontDefinition(
        key="source_sans_3",
        display_name="Source Sans 3",
        regular_file="source_sans_3/SourceSans3-Regular.ttf",
        bold_file="source_sans_3/SourceSans3-Bold.ttf",
    ),
    "libre_baskerville": FontDefinition(
        key="libre_baskerville",
        display_name="Libre Baskerville",
        regular_file="libre_baskerville/LibreBaskerville-Regular.ttf",
        bold_file="libre_baskerville/LibreBaskerville-Bold.ttf",
    ),
    "liberation_serif": FontDefinition(
        key="liberation_serif",
        display_name="Liberation Serif",
        regular_file="liberation_serif/LiberationSerif-Regular.ttf",
        bold_file="liberation_serif/LiberationSerif-Bold.ttf",
    ),
    "liberation_sans": FontDefinition(
        key="liberation_sans",
        display_name="Liberation Sans",
        regular_file="liberation_sans/LiberationSans-Regular.ttf",
        bold_file="liberation_sans/LiberationSans-Bold.ttf",
    ),
}


def canonicalize_font_key(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    for key, definition in FONT_DEFINITIONS.items():
        display_normalized = definition.display_name.lower().replace(" ", "_")
        if normalized in {key, display_normalized}:
            return key
    raise KeyError(f"Unknown font family: {value}")


def ensure_font_files(font_keys: list[str] | None = None) -> None:
    keys = font_keys or list(FONT_DEFINITIONS)
    missing: list[str] = []
    for key in keys:
        definition = FONT_DEFINITIONS[key]
        for relative_path in (definition.regular_file, definition.bold_file):
            path = FONTS_DIR / relative_path
            if not path.exists():
                missing.append(str(path))
    if missing:
        missing_text = "\n".join(missing)
        raise FileNotFoundError(
            "Required bundled fonts are missing.\n"
            "Run `python scripts/download_fonts.py` before generating PDFs.\n"
            f"Missing files:\n{missing_text}"
        )


def register_fonts(font_keys: list[str] | None = None) -> dict[str, RegisteredFontFamily]:
    keys = font_keys or list(FONT_DEFINITIONS)
    ensure_font_files(keys)
    registry: dict[str, RegisteredFontFamily] = {}
    registered_names = set(pdfmetrics.getRegisteredFontNames())
    for key in keys:
        definition = FONT_DEFINITIONS[key]
        regular_name = f"pdfag-{key}-regular"
        bold_name = f"pdfag-{key}-bold"
        regular_path = FONTS_DIR / definition.regular_file
        bold_path = FONTS_DIR / definition.bold_file
        if regular_name not in registered_names:
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
            registered_names.add(regular_name)
        if bold_name not in registered_names:
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            registered_names.add(bold_name)
        registry[key] = RegisteredFontFamily(
            key=key,
            display_name=definition.display_name,
            regular_name=regular_name,
            bold_name=bold_name,
        )
    return registry
