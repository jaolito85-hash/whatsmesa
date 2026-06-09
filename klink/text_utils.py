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


def format_brl(value: float) -> str:
    """Formata 121.0 -> '121,00' e 1234.5 -> '1.234,50' (padrão brasileiro)."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

