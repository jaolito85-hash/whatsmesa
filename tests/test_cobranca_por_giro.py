from __future__ import annotations

import tempfile
import unittest

from klink.billing_service import BillingService
from klink.storage import Database
from klink.table_session_service import TableSessionService


def make_environment(require_validation: bool = False):
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    billing = BillingService(db)
    sessions = TableSessionService(db, billing=billing, require_validation=require_validation)
    return db, sessions, billing


def count_mesa_aberta(db: Database) -> int:
    rows = db.fetchall("select id from billing_events where tipo = 'mesa_aberta'")
    return len(rows)


class CobrancaPorGiroTest(unittest.TestCase):
    """Cobrança por OCUPAÇÃO física da mesa (giro), não por celular.

    A promessa de venda é 'R$ 3,97 por mesa aberta'. Antes, 4 amigos na mesma
    mesa, cada um escaneando o QR, viravam 4 cobranças — fatura até 4x maior
    que o prometido. Agora todos caem no mesmo giro: UMA cobrança."""

    def test_quatro_celulares_na_mesma_mesa_uma_cobranca(self):
        db, sessions, _billing = make_environment()
        for i in range(4):
            sessions.activate_from_message(f"551190000004{i}", "Mesa 6")
        self.assertEqual(count_mesa_aberta(db), 1)

    def test_mesas_diferentes_cobram_separado(self):
        db, sessions, _billing = make_environment()
        sessions.activate_from_message("5511900000050", "Mesa 1")
        sessions.activate_from_message("5511900000051", "Mesa 2")
        self.assertEqual(count_mesa_aberta(db), 2)

    def test_novo_giro_apos_fechar_cobra_de_novo(self):
        db, sessions, _billing = make_environment()
        s1 = sessions.activate_from_message("5511900000052", "Mesa 4")
        sessions.close_session(s1["id"])
        # Outro grupo senta na mesma mesa depois: novo giro, nova cobrança.
        sessions.activate_from_message("5511900000053", "Mesa 4")
        self.assertEqual(count_mesa_aberta(db), 2)

    def test_validacao_de_varios_celulares_na_mesma_mesa_cobra_uma_vez(self):
        db, sessions, _billing = make_environment(require_validation=True)
        s1 = sessions.activate_from_message("5511900000054", "Mesa 8")
        s2 = sessions.activate_from_message("5511900000055", "Mesa 8")
        sessions.validate_session(s1["id"])
        sessions.validate_session(s2["id"])
        self.assertEqual(count_mesa_aberta(db), 1)


class MesaSoLiberaNaUltimaSessaoTest(unittest.TestCase):
    """Fechar a conta de UM celular não pode marcar a mesa como livre se os
    amigos dele ainda estão pedindo nela."""

    def test_fechar_uma_de_duas_sessoes_mantem_mesa_ocupada(self):
        db, sessions, _billing = make_environment()
        s1 = sessions.activate_from_message("5511900000060", "Mesa 9")
        s2 = sessions.activate_from_message("5511900000061", "Mesa 9")
        token_antes = db.fetchone(
            "select qr_token_atual from mesas where id = ?", (s1["mesa_id"],)
        )["qr_token_atual"]

        sessions.close_session(s1["id"])

        mesa = db.fetchone(
            "select status, qr_token_atual from mesas where id = ?", (s1["mesa_id"],)
        )
        self.assertNotEqual(mesa["status"], "mesa_livre")
        self.assertEqual(mesa["qr_token_atual"], token_antes, "giro não pode rotacionar")

        sessions.close_session(s2["id"])
        mesa = db.fetchone(
            "select status, qr_token_atual from mesas where id = ?", (s1["mesa_id"],)
        )
        self.assertEqual(mesa["status"], "mesa_livre")
        self.assertNotEqual(mesa["qr_token_atual"], token_antes)

    def test_recusar_um_celular_mantem_mesa_do_outro(self):
        db, sessions, _billing = make_environment(require_validation=True)
        s1 = sessions.activate_from_message("5511900000062", "Mesa 10")
        s2 = sessions.activate_from_message("5511900000063", "Mesa 10")
        sessions.validate_session(s1["id"])

        sessions.reject_session(s2["id"])

        mesa = db.fetchone("select status from mesas where id = ?", (s1["mesa_id"],))
        self.assertNotEqual(mesa["status"], "mesa_livre")


if __name__ == "__main__":
    unittest.main()
