from __future__ import annotations

from .text_utils import normalize_text


SUPPORTED_LANGUAGES = ("pt", "en", "es")

EN_MARKERS = {
    "another",
    "bill",
    "can",
    "change",
    "check",
    "confirm",
    "fries",
    "get",
    "please",
    "send",
    "table",
    "waiter",
    "water",
    "yes",
}

ES_MARKERS = {
    "camarero",
    "cambiar",
    "confirmar",
    "confirmo",
    "cuenta",
    "dame",
    "limon",
    "mesero",
    "otra",
    "papas",
    "patatas",
    "puedes",
    "quiero",
    "servilleta",
    "si",
}

PT_MARKERS = {
    "alterar",
    "batata",
    "confirma",
    "conta",
    "garcom",
    "guardanapo",
    "manda",
    "porcao",
}

EN_PHRASES = ("can i", "i want", "same again", "another round", "close the bill")
ES_PHRASES = ("por favor", "me das", "otra ronda", "la cuenta", "cerrar la cuenta")
PT_PHRASES = ("me ve", "pode mandar", "outra rodada", "fecha a conta")


def detect_language(text: str) -> str:
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    scores = {
        "pt": len(tokens & PT_MARKERS),
        "en": len(tokens & EN_MARKERS),
        "es": len(tokens & ES_MARKERS),
    }

    for phrase in EN_PHRASES:
        if phrase in normalized:
            scores["en"] += 2
    for phrase in ES_PHRASES:
        if phrase in normalized:
            scores["es"] += 2
    for phrase in PT_PHRASES:
        if phrase in normalized:
            scores["pt"] += 2

    winner = max(scores, key=scores.get)
    return winner if scores[winner] > 0 else "pt"
