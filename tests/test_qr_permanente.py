from __future__ import annotations

import tempfile
import unittest

from klink.config import Settings
from klink.qr_service import QRService
from klink.storage import Database
from klink.table_session_service import TableSessionService


def make():
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    sessions = TableSessionService(db)
    settings = Settings(
        database_path=handle.name,
        public_base_url="https://klinkai.com.br",
        whatsapp_phone="5511999998888",
        evolution_api_url="",
        evolution_api_key="",
        evolution_instance="",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        supabase_url="",
        supabase_service_role_key="",
        admin_token="",
        dashboard_user="admin",
        dashboard_password="",
    )
    qr = QRService(settings, sessions)
    return db, sessions, qr


class QRPermanenteTest(unittest.TestCase):
    def test_qr_pelo_id_da_mesa_resolve(self):
        _db, sessions, qr = make()
        mesa = sessions.table_by_number(5)
        link = qr.resolve_redirect(mesa["id"])
        self.assertIsNotNone(link)
        self.assertIn("Mesa%205", link)

    def test_qr_impresso_continua_valendo_depois_de_fechar(self):
        """O coração da correção: o QR colado na mesa NÃO pode quebrar quando a
        conta fecha (mesmo o token rotativo mudando)."""
        db, sessions, qr = make()
        mesa = sessions.table_by_number(7)
        mesa_id = mesa["id"]

        # QR impresso (id permanente) funciona antes de qualquer uso
        self.assertIsNotNone(qr.resolve_redirect(mesa_id))

        # grupo abre a mesa e depois fecha a conta (token rotativo muda aqui)
        session = sessions.activate_from_message("5511900000001", "Mesa 7")
        token_antes = db.fetchone(
            "select qr_token_atual from mesas where id = ?", (mesa_id,)
        )["qr_token_atual"]
        sessions.close_session(session["id"])
        token_depois = db.fetchone(
            "select qr_token_atual from mesas where id = ?", (mesa_id,)
        )["qr_token_atual"]

        # o token rotativo de fato mudou (segurança de link dinâmico preservada)
        self.assertNotEqual(token_antes, token_depois)
        # ...mas o QR impresso (id permanente) CONTINUA resolvendo
        self.assertIsNotNone(qr.resolve_redirect(mesa_id))

    def test_token_rotativo_antigo_para_de_valer_mas_id_permanece(self):
        db, sessions, qr = make()
        mesa = sessions.table_by_number(3)
        mesa_id = mesa["id"]
        session = sessions.activate_from_message("5511900000002", "Mesa 3")
        token_antigo = db.fetchone(
            "select qr_token_atual from mesas where id = ?", (mesa_id,)
        )["qr_token_atual"]

        sessions.close_session(session["id"])

        # link dinâmico antigo morre (comportamento de segurança mantido)
        self.assertIsNone(qr.resolve_redirect(token_antigo))
        # QR permanente continua firme
        self.assertIsNotNone(qr.resolve_redirect(mesa_id))

    def test_ciclo_abre_fecha_reabre_pelo_mesmo_qr(self):
        _db, sessions, qr = make()
        mesa = sessions.table_by_number(2)
        mesa_id = mesa["id"]

        # 1º grupo
        s1 = sessions.activate_from_message("5511900000010", "Mesa 2")
        self.assertIsNotNone(s1)
        sessions.close_session(s1["id"])

        # 2º grupo escaneia o MESMO QR impresso e consegue abrir de novo
        self.assertIsNotNone(qr.resolve_redirect(mesa_id))
        s2 = sessions.activate_from_message("5511900000011", "Mesa 2")
        self.assertIsNotNone(s2)
        self.assertNotEqual(s1["id"], s2["id"])

    def test_id_inexistente_nao_resolve(self):
        _db, _sessions, qr = make()
        self.assertIsNone(qr.resolve_redirect("nao-existe-12345"))


if __name__ == "__main__":
    unittest.main()
