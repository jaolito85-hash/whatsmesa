from __future__ import annotations

import tempfile
import unittest

from klink.storage import DEMO_SLUG, Database, slugify


def make_db() -> Database:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return db


def only_restaurant(db: Database) -> dict:
    return db.fetchone("select * from restaurantes limit 1")


class SlugifyTest(unittest.TestCase):
    def test_remove_acentos_e_espacos(self):
        self.assertEqual(slugify("Bar do João"), "bar-do-joao")

    def test_simbolos_viram_hifen(self):
        self.assertEqual(slugify("  Café & Cia!! "), "cafe-cia")

    def test_vazio_tem_fallback(self):
        self.assertEqual(slugify("!!!"), "restaurante")


class MigrateLegacyDataTest(unittest.TestCase):
    def test_renomeia_mesazap_e_corrige_preco(self):
        db = make_db()
        rid = only_restaurant(db)["id"]
        # Simula dados gravados por uma versão antiga.
        db.execute(
            "update restaurantes set nome='MesaZap Demo', slug='mesazap-demo' where id=?",
            (rid,),
        )
        db.execute(
            "update billing_accounts set preco_por_pedido=1.97 where restaurante_id=?",
            (rid,),
        )

        db.migrate_legacy_data()

        restaurant = only_restaurant(db)
        self.assertEqual(restaurant["nome"], "Klink Demo")
        self.assertEqual(restaurant["slug"], DEMO_SLUG)
        account = db.fetchone(
            "select preco_por_pedido from billing_accounts where restaurante_id=?",
            (rid,),
        )
        self.assertAlmostEqual(account["preco_por_pedido"], 3.97, places=2)

    def test_nao_mexe_em_restaurante_ja_configurado(self):
        db = make_db()
        rid = only_restaurant(db)["id"]
        db.update_restaurant(rid, nome="Bar do Zé")

        db.migrate_legacy_data()

        restaurant = only_restaurant(db)
        self.assertEqual(restaurant["nome"], "Bar do Zé")
        self.assertEqual(restaurant["slug"], "bar-do-ze")

    def test_preco_configurado_diferente_de_197_nao_muda(self):
        db = make_db()
        rid = only_restaurant(db)["id"]
        db.execute(
            "update billing_accounts set preco_por_pedido=5.00 where restaurante_id=?",
            (rid,),
        )
        db.migrate_legacy_data()
        account = db.fetchone(
            "select preco_por_pedido from billing_accounts where restaurante_id=?",
            (rid,),
        )
        self.assertAlmostEqual(account["preco_por_pedido"], 5.00, places=2)


class UpdateRestaurantTest(unittest.TestCase):
    def test_seed_comeca_como_demo(self):
        db = make_db()
        self.assertEqual(only_restaurant(db)["slug"], DEMO_SLUG)

    def test_definir_nome_gera_slug_e_sai_do_demo(self):
        db = make_db()
        rid = only_restaurant(db)["id"]

        db.update_restaurant(rid, nome="Boteco Central", telefone_whatsapp="11998887766")

        restaurant = only_restaurant(db)
        self.assertEqual(restaurant["nome"], "Boteco Central")
        self.assertEqual(restaurant["slug"], "boteco-central")
        self.assertNotEqual(restaurant["slug"], DEMO_SLUG)
        self.assertEqual(restaurant["telefone_whatsapp"], "11998887766")

    def test_atualizar_so_telefone_mantem_nome_e_slug(self):
        db = make_db()
        rid = only_restaurant(db)["id"]
        db.update_restaurant(rid, telefone_whatsapp="5511999990000")
        restaurant = only_restaurant(db)
        self.assertEqual(restaurant["slug"], DEMO_SLUG)
        self.assertEqual(restaurant["telefone_whatsapp"], "5511999990000")


if __name__ == "__main__":
    unittest.main()
