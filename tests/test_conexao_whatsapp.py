from __future__ import annotations

import importlib
import os
import tempfile
import unittest


class ConexaoWhatsAppTest(unittest.TestCase):
    """Estado REAL da conexão do WhatsApp (evento CONNECTION_UPDATE da Evolution).

    Antes, o selo 'Bot conectado' só verificava se as variáveis de ambiente
    estavam preenchidas — número banido continuava com selo verde e o
    restaurante ficava surdo sem ninguém saber."""

    _KEYS = (
        "KLINK_DATABASE",
        "KLINK_DASHBOARD_PASSWORD",
        "KLINK_WEBHOOK_SECRET",
        "KLINK_DEV_MODE",
        "EVOLUTION_API_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE",
    )

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
            "EVOLUTION_API_URL": "http://evolution.local",
            "EVOLUTION_API_KEY": "chave-teste",
            "EVOLUTION_INSTANCE": "instancia-teste",
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

    def _connection_update(self, state: str):
        return self.client.post(
            "/webhook",
            json={"event": "connection.update", "data": {"state": state}},
        )

    def test_estado_desconhecido_antes_de_qualquer_evento(self):
        health = self.client.get("/health").get_json()
        self.assertEqual(health["whatsapp"]["connection_state"], "desconhecido")
        self.assertFalse(health["whatsapp"]["connected"])
        self.assertEqual(health["alerts"], [])

    def test_evento_close_liga_o_alerta(self):
        r = self._connection_update("close")
        self.assertEqual(r.status_code, 200)

        health = self.client.get("/health").get_json()
        self.assertEqual(health["whatsapp"]["connection_state"], "close")
        self.assertFalse(health["whatsapp"]["connected"])
        self.assertIn("whatsapp_desconectado", health["alerts"])

    def test_evento_open_desliga_o_alerta(self):
        self._connection_update("close")
        self._connection_update("open")

        health = self.client.get("/health").get_json()
        self.assertEqual(health["whatsapp"]["connection_state"], "open")
        self.assertTrue(health["whatsapp"]["connected"])
        self.assertNotIn("whatsapp_desconectado", health["alerts"])

    def test_evento_maiusculo_da_evolution_v1_funciona(self):
        r = self.client.post(
            "/webhook",
            json={"event": "CONNECTION_UPDATE", "data": {"state": "close"}},
        )
        self.assertEqual(r.status_code, 200)
        health = self.client.get("/health").get_json()
        self.assertEqual(health["whatsapp"]["connection_state"], "close")

    def test_dashboard_api_inclui_estado_do_whatsapp(self):
        self._connection_update("close")
        data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(data["whatsapp"]["state"], "close")
        self.assertTrue(data["whatsapp"]["configured"])

    def test_config_mostra_desconectado(self):
        self._connection_update("close")
        page = self.client.get("/config")
        self.assertIn("DESCONECTADO".encode("utf-8"), page.data)

    def test_config_mostra_conectado_so_com_estado_open(self):
        self._connection_update("open")
        page = self.client.get("/config")
        self.assertIn("Bot conectado".encode("utf-8"), page.data)


if __name__ == "__main__":
    unittest.main()
