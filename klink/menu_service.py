from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .storage import Database
from .text_utils import normalize_text


NUMBER_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "one": 1,
    "a": 1,
    "an": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}


@dataclass(frozen=True)
class MenuMatch:
    product_id: str
    nome: str
    quantidade: int
    preco: float
    setor: str
    observacoes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "nome": self.nome,
            "quantidade": self.quantidade,
            "preco": self.preco,
            "setor": self.setor,
            "observacoes": self.observacoes,
        }


class MenuService:
    def __init__(self, db: Database):
        self.db = db

    def products_for_restaurant(self, restaurante_id: str) -> list[dict[str, Any]]:
        products = self.db.fetchall(
            """
            select id, nome, descricao, preco, categoria, setor, ativo, disponivel
            from produtos
            where restaurante_id = ? and ativo = 1
            order by setor, categoria, nome
            """,
            (restaurante_id,),
        )
        for product in products:
            product["aliases"] = [
                row["alias"]
                for row in self.db.fetchall(
                    "select alias from produto_aliases where produto_id = ? order by length(alias) desc",
                    (product["id"],),
                )
            ]
        return products

    def find_items(self, restaurante_id: str, text: str) -> dict[str, Any]:
        normalized = normalize_text(text)
        products = self.products_for_restaurant(restaurante_id)
        ambiguous = self._find_ambiguous_brahma(normalized, products)
        if ambiguous:
            return {
                "items": [],
                "ambiguous": ambiguous,
                "unavailable": [],
                "missing_terms": [],
            }

        matches_by_product: dict[str, MenuMatch] = {}
        unavailable: list[dict[str, Any]] = []

        for product in products:
            aliases = sorted(product["aliases"], key=lambda item: len(item), reverse=True)
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm:
                    continue
                pattern = rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])"
                match = re.search(pattern, normalized)
                if not match:
                    continue

                quantity = self._quantity_before(normalized, match.start())
                if not product["disponivel"]:
                    unavailable.append({"nome": product["nome"], "motivo": "indisponivel"})
                    break

                existing = matches_by_product.get(product["id"])
                if existing:
                    quantity += existing.quantidade

                matches_by_product[product["id"]] = MenuMatch(
                    product_id=product["id"],
                    nome=product["nome"],
                    quantidade=quantity,
                    preco=float(product["preco"]),
                    setor=product["setor"],
                )
                break

        return {
            "items": [match.as_dict() for match in matches_by_product.values()],
            "ambiguous": [],
            "unavailable": unavailable,
            "missing_terms": [],
        }

    def product_by_name_or_alias(
        self, restaurante_id: str, requested_name: str
    ) -> dict[str, Any] | None:
        requested = normalize_text(requested_name)
        if not requested:
            return None

        rows = self.db.fetchall(
            """
            select p.*
            from produtos p
            left join produto_aliases a on a.produto_id = p.id
            where p.restaurante_id = ?
              and p.ativo = 1
              and (lower(p.nome) = lower(?) or lower(a.alias) = lower(?))
            order by p.nome
            """,
            (restaurante_id, requested_name, requested_name),
        )
        if rows:
            return rows[0]

        for product in self.products_for_restaurant(restaurante_id):
            names = [product["nome"], *product["aliases"]]
            if any(normalize_text(name) == requested for name in names):
                return product
        return None

    def _quantity_before(self, normalized_text: str, start: int) -> int:
        before = normalized_text[:start].strip()
        if not before:
            return 1

        tokens = before.split()
        last_connector = max(
            (index for index, token in enumerate(tokens) if token in {"e", "and", "y"}),
            default=-1,
        )
        tail = tokens[last_connector + 1 :][-4:]
        if not tail:
            return 1

        for token in reversed(tail):
            if token.isdigit():
                return max(1, int(token))
            if token in NUMBER_WORDS:
                return NUMBER_WORDS[token]
        return 1

    def _find_ambiguous_brahma(
        self, normalized_text: str, products: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if "brahma" not in normalized_text:
            return []
        if any(word in normalized_text for word in ["600", "600ml", "garrafa", "lata"]):
            return []

        brahma_options = [
            {"id": product["id"], "nome": product["nome"]}
            for product in products
            if normalize_text(product["nome"]).startswith("brahma")
        ]
        return brahma_options if len(brahma_options) > 1 else []
