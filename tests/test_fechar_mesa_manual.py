from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from klink.storage import Database
from klink.table_session_service import TableSessionService


def make_service() -> tuple[TableSessionService, Database]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return TableSessionService(db), db


class CloseTableServiceTest(unittest.TestCase):
    """Fechar mesa manualmente pelo painel: cobre o caso mais comum no Brasil —
    o cliente paga no caixa e vai embora sem mandar 'fecha a conta' no bot."""

    def test_fecha_todas_as_sessoes_da_mesa(self):
        service, db = make_service()
        # Dois celulares diferentes na mesma mesa = duas sessões ativas.
        s1 = service.activate_from_message("5511900000010", "Mesa 5")
        s2 = service.activate_from_message("5511900000011", "Mesa 5")
        self.assertEqual(s1["mesa_id"], s2["mesa_id"])

        closed = service.close_table(s1["mesa_id"])

        self.assertEqual(closed, 2)
        for session_id in (s1["id"], s2["id"]):
            row = db.fetchone("select status from sessoes_mesa where id = ?", (session_id,))
            self.assertEqual(row["status"], "sessao_fechada")
        mesa = db.fetchone("select status from mesas where id = ?", (s1["mesa_id"],))
        self.assertEqual(mesa["status"], "mesa_livre")

    def test_mesa_ocupada_sem_sessao_e_liberada(self):
        service, db = make_service()
        # As mesas da demo nascem com status 'mesa_ocupada' sem sessão nenhuma.
        mesa = db.fetchone("select id, status from mesas where numero = 3")
        self.assertEqual(mesa["status"], "mesa_ocupada")

        closed = service.close_table(mesa["id"])

        self.assertEqual(closed, 0)
        after = db.fetchone("select status from mesas where id = ?", (mesa["id"],))
        self.assertEqual(after["status"], "mesa_livre")

    def test_fechar_mesa_e_idempotente(self):
        service, db = make_service()
        session = service.activate_from_message("5511900000012", "Mesa 8")

        self.assertEqual(service.close_table(session["mesa_id"]), 1)
        self.assertEqual(service.close_table(session["mesa_id"]), 0)


class CloseTableRouteTest(unittest.TestCase):
    _KEYS = ("KLINK_DATABASE", "KLINK_DASHBOARD_PASSWORD", "KLINK_WEBHOOK_SECRET", "KLINK_DEV_MODE")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}
        for key, value in {
            "KLINK_DATABASE": self._db_path,
            "KLINK_DASHBOARD_PASSWORD": "",
            "KLINK_WEBHOOK_SECRET": None,
            "KLINK_DEV_MODE": None,
        }.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from klink import config as config_module

        importlib.reload(config_module)
        import app as app_module

        importlib.reload(app_module)
        self.client = app_module.app.test_client()

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_rota_fecha_mesa_com_sessao(self):
        # Abre uma sessão de verdade pelo webhook.
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000013@s.whatsapp.net", "id": "msg-fm-1"},
                    "message": {"conversation": "Mesa 2"},
                }
            },
        )
        tables = self.client.get("/api/tables").get_json()["tables"]
        mesa = next(t for t in tables if t["numero"] == 2)
        self.assertGreaterEqual(mesa["sessoes_abertas"], 1)

        r = self.client.post(f"/api/tables/{mesa['id']}/close")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["sessoes_fechadas"], 1)
        tables = self.client.get("/api/tables").get_json()["tables"]
        mesa = next(t for t in tables if t["numero"] == 2)
        self.assertEqual(mesa["sessoes_abertas"], 0)
        self.assertEqual(mesa["status"], "mesa_livre")

    def test_rota_mesa_inexistente_retorna_404(self):
        r = self.client.post("/api/tables/nao-existe/close")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
