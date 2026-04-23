from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", ascii_text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def compact_text(value: str) -> str:
    return normalize_text(value).replace(" ", "")

