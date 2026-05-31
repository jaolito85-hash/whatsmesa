from __future__ import annotations

import tempfile
import unittest

from klink.menu_service import MenuService
from klink.storage import Database


def make_db() -> Database:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return db


def rid(db: Database) -> str:
    return db.fetchone("select id from restaurantes limit 1")["id"]


def find(db: Database, restaurante_id: str, produto_id: str) -> dict | None:
    for p in MenuService(db).products_for_restaurant(restaurante_id):
        if p["id"] == produto_id:
            return p
    return None


class CreateProductTest(unittest.TestCase):
    def test_cria_produto_com_apelidos(self):
        db = make_db()
        r = rid(db)
        pid = db.create_product(
            r, nome="Suco de Laranja", preco=9.5, setor="bar",
            categoria="bebida", aliases=["suco", "suquinho", "orange juice"],
        )
        novo = find(db, r, pid)
        self.assertIsNotNone(novo)
        self.assertEqual(novo["nome"], "Suco de Laranja")
        self.assertEqual(novo["preco"], 9.5)
        self.assertEqual(novo["setor"], "bar")
        self.assertGreaterEqual({a.lower() for a in novo["aliases"]}, {"suco", "suquinho"})

    def test_dedup_de_apelidos(self):
        db = make_db()
        r = rid(db)
        pid = db.create_product(r, nome="X", preco=1, setor="bar", aliases=["suco", "Suco", " suco "])
        novo = find(db, r, pid)
        self.assertEqual(len(novo["aliases"]), 1)

    def test_ia_reconhece_pelo_apelido(self):
        """O teste que mais importa: produto cadastrado + apelido => a IA acha no pedido."""
        db = make_db()
        r = rid(db)
        db.create_product(r, nome="Suco de Laranja", preco=9.5, setor="bar", aliases=["suco"])
        result = MenuService(db).find_items(r, "me ve um suco por favor")
        nomes = [item["nome"] for item in result["items"]]
        self.assertIn("Suco de Laranja", nomes)


class UpdateProductTest(unittest.TestCase):
    def test_atualiza_campos_e_substitui_apelidos(self):
        db = make_db()
        r = rid(db)
        pid = db.create_product(r, nome="Suco", preco=9.5, setor="bar", aliases=["suco"])
        db.update_product(
            pid, nome="Suco Natural", preco=11.0, setor="cozinha", aliases=["suco natural"]
        )
        novo = find(db, r, pid)
        self.assertEqual(novo["nome"], "Suco Natural")
        self.assertEqual(novo["preco"], 11.0)
        self.assertEqual(novo["setor"], "cozinha")
        self.assertEqual({a.lower() for a in novo["aliases"]}, {"suco natural"})


class DeactivateProductTest(unittest.TestCase):
    def test_remover_some_do_cardapio(self):
        db = make_db()
        r = rid(db)
        pid = db.create_product(r, nome="Temp", preco=1, setor="bar")
        db.deactivate_product(pid)
        self.assertIsNone(find(db, r, pid))


class ProductOwnershipTest(unittest.TestCase):
    def test_isolamento_por_restaurante(self):
        db = make_db()
        r = rid(db)
        pid = db.create_product(r, nome="X", preco=1, setor="bar")
        self.assertTrue(db.product_belongs_to(r, pid))
        self.assertFalse(db.product_belongs_to("outro-restaurante", pid))
        db.deactivate_product(pid)
        self.assertFalse(db.product_belongs_to(r, pid))  # inativo não conta


if __name__ == "__main__":
    unittest.main()
