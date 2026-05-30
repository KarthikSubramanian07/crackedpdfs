from __future__ import annotations

import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from random import Random
from typing import Any


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "snippets"


@lru_cache(maxsize=1)
def load_snippet_bank() -> dict[str, Any]:
    bank: dict[str, Any] = {}
    for path in sorted(ASSETS_ROOT.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            bank[path.stem] = json.load(handle)
    return bank


def choose(rng: Random, values: list[str]) -> str:
    return rng.choice(values)


def choose_many(rng: Random, values: list[str], count: int) -> list[str]:
    if count <= 0:
        return []
    if count >= len(values):
        items = list(values)
        rng.shuffle(items)
        return items
    return rng.sample(values, count)


def join_sentences(sentences: list[str]) -> str:
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())


def make_person_name(rng: Random, bank: dict[str, Any]) -> str:
    common = bank["common"]
    return f"{choose(rng, common['people_first_names'])} {choose(rng, common['people_last_names'])}"


def make_date_text(rng: Random, bank: dict[str, Any]) -> str:
    month = choose(rng, bank["common"]["months"])
    day = rng.randint(1, 28)
    year = int(choose(rng, bank["common"]["years"]))
    return f"{month} {day}, {year}"


def make_course_term(rng: Random) -> str:
    return choose(rng, ["Spring Term", "Summer Session", "Fall Term", "Winter Session"])


def make_course_line(rng: Random, bank: dict[str, Any]) -> str:
    course = choose(rng, bank["academic"]["courses"])
    return f"{course} | {make_course_term(rng)} | {make_date_text(rng, bank)}"


def make_department_line(rng: Random, bank: dict[str, Any]) -> str:
    common = bank["common"]
    return (
        f"{choose(rng, common['departments'])} | "
        f"{choose(rng, common['locations'])} | {make_date_text(rng, bank)}"
    )


def make_reference_id(rng: Random, prefix: str) -> str:
    return f"{prefix}-{rng.randint(10000, 99999)}"


def sentence_paragraph(
    rng: Random,
    sentences: list[str],
    min_count: int,
    max_count: int,
) -> str:
    count = rng.randint(min_count, max_count)
    return join_sentences(choose_many(rng, sentences, count))


def make_content_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return sha256(encoded).hexdigest()
