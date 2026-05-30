from __future__ import annotations

import io
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT / "assets" / "fonts"

RAW_FONTS = {
    "source_serif_4/SourceSerif4-Regular.ttf": (
        "https://raw.githubusercontent.com/adobe-fonts/source-serif/release/TTF/"
        "SourceSerif4-Regular.ttf"
    ),
    "source_serif_4/SourceSerif4-Bold.ttf": (
        "https://raw.githubusercontent.com/adobe-fonts/source-serif/release/TTF/"
        "SourceSerif4-Bold.ttf"
    ),
    "source_sans_3/SourceSans3-Regular.ttf": (
        "https://raw.githubusercontent.com/adobe-fonts/source-sans/release/TTF/"
        "SourceSans3-Regular.ttf"
    ),
    "source_sans_3/SourceSans3-Bold.ttf": (
        "https://raw.githubusercontent.com/adobe-fonts/source-sans/release/TTF/"
        "SourceSans3-Bold.ttf"
    ),
    "libre_baskerville/LibreBaskerville-Regular.ttf": (
        "https://raw.githubusercontent.com/impallari/Libre-Baskerville/master/fonts/ttf/"
        "LibreBaskerville-Regular.ttf"
    ),
    "libre_baskerville/LibreBaskerville-Bold.ttf": (
        "https://raw.githubusercontent.com/impallari/Libre-Baskerville/master/fonts/ttf/"
        "LibreBaskerville-Bold.ttf"
    ),
}

RAW_TEXT = {
    "source_serif_4/OFL.txt": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sourceserif4/OFL.txt"
    ),
    "source_sans_3/OFL.txt": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/OFL.txt"
    ),
    "libre_baskerville/OFL.txt": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/librebaskerville/OFL.txt"
    ),
}

LIBERATION_RELEASE = (
    "https://github.com/liberationfonts/liberation-fonts/files/7261482/"
    "liberation-fonts-ttf-2.1.5.tar.gz"
)

LIBERATION_MEMBERS = {
    "LiberationSerif-Regular.ttf": "liberation_serif/LiberationSerif-Regular.ttf",
    "LiberationSerif-Bold.ttf": "liberation_serif/LiberationSerif-Bold.ttf",
    "LiberationSans-Regular.ttf": "liberation_sans/LiberationSans-Regular.ttf",
    "LiberationSans-Bold.ttf": "liberation_sans/LiberationSans-Bold.ttf",
    "LICENSE": "liberation_sans/LICENSE",
}


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def write_bytes(relative_path: str, content: bytes) -> None:
    destination = FONTS_DIR / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def write_text(relative_path: str, content: bytes) -> None:
    destination = FONTS_DIR / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content.decode("utf-8"), encoding="utf-8")


def download_liberation() -> None:
    archive_bytes = download(LIBERATION_RELEASE)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            target_name = member.name.rsplit("/", 1)[-1]
            if target_name not in LIBERATION_MEMBERS:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            destination = LIBERATION_MEMBERS[target_name]
            write_bytes(destination, extracted.read())
    source_license = FONTS_DIR / "liberation_sans" / "LICENSE"
    if source_license.exists():
        write_bytes("liberation_serif/LICENSE", source_license.read_bytes())


def main() -> None:
    for relative_path, url in RAW_FONTS.items():
        write_bytes(relative_path, download(url))
    for relative_path, url in RAW_TEXT.items():
        write_text(relative_path, download(url))
    download_liberation()


if __name__ == "__main__":
    main()
