from __future__ import annotations

import tempfile
import unittest

from klink.audio_service import _ensure_public_url
from klink.billing_service import BillingService
from klink.storage import Database
from klink.table_session_service import TableSessionService


def make_db() -> Database:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return db


def restaurant_id(db: Database) -> str:
    return db.fetchone("select id from restaurantes limit 1")["id"]


class RejectSessionTest(unittest.TestCase):
    def test_nao_recusa_sessao_ja_ativa(self):
        """M-3: rejeitar uma sessão ATIVA (já cobrada) não deve ter efeito —
        senão geraria cobrança órfã. Encerrar ativa é via close_session."""
        db = make_db()
        sessions = TableSessionService(db, billing=BillingService(db), require_validation=False)
        s = sessions.activate_from_message("5511900000099", "Mesa 4")
        self.assertEqual(s["status"], "sessao_ativa")

        sessions.reject_session(s["id"])

        after = db.fetchone("select status from sessoes_mesa where id = ?", (s["id"],))
        self.assertEqual(after["status"], "sessao_ativa")  # continua ativa, não recusada

    def test_recusa_sessao_pendente(self):
        db = make_db()
        sessions = TableSessionService(db, require_validation=True)
        s = sessions.activate_from_message("5511900000098", "Mesa 6")
        self.assertEqual(s["status"], "sessao_pendente")

        sessions.reject_session(s["id"])

        after = db.fetchone("select status from sessoes_mesa where id = ?", (s["id"],))
        self.assertEqual(after["status"], "sessao_recusada")


class InvoiceIdempotencyTest(unittest.TestCase):
    def test_generate_invoice_e_idempotente(self):
        db = make_db()
        billing = BillingService(db)
        rid = restaurant_id(db)
        f1 = billing.generate_invoice(rid, "2026-05")
        f2 = billing.generate_invoice(rid, "2026-05")
        self.assertEqual(f1["id"], f2["id"])

    def test_mark_invoice_paid_e_idempotente(self):
        db = make_db()
        billing = BillingService(db)
        rid = restaurant_id(db)
        fatura = billing.generate_invoice(rid, "2026-05")

        primeira = billing.mark_invoice_paid(fatura["id"])
        self.assertEqual(primeira["status"], "paga")
        paga_em_1 = primeira["paga_em"]

        segunda = billing.mark_invoice_paid(fatura["id"])  # não pode quebrar
        self.assertEqual(segunda["status"], "paga")
        self.assertEqual(segunda["paga_em"], paga_em_1)  # não re-carimba

    def test_mark_invoice_paid_inexistente_retorna_none(self):
        db = make_db()
        billing = BillingService(db)
        self.assertIsNone(billing.mark_invoice_paid("nao-existe"))


class SSRFGuardTest(unittest.TestCase):
    def test_bloqueia_metadata_cloud(self):
        with self.assertRaises(ValueError):
            _ensure_public_url("http://169.254.169.254/latest/meta-data/")

    def test_bloqueia_loopback(self):
        with self.assertRaises(ValueError):
            _ensure_public_url("http://127.0.0.1:6379/")

    def test_bloqueia_rede_privada(self):
        with self.assertRaises(ValueError):
            _ensure_public_url("http://10.0.0.5/audio.ogg")

    def test_bloqueia_esquema_nao_http(self):
        with self.assertRaises(ValueError):
            _ensure_public_url("file:///etc/passwd")

    def test_permite_ip_publico(self):
        # não deve levantar erro
        _ensure_public_url("https://8.8.8.8/audio.ogg")


if __name__ == "__main__":
    unittest.main()
