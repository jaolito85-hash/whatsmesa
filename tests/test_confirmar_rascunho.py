from __future__ import annotations

import importlib
import os
import tempfile
import unittest


class ConfirmarRascunhoTest(unittest.TestCase):
    """Cliente que não responde '1' deixava o pedido morrer em rascunho — a
    comida nunca chegava na cozinha e nem o garçom conseguia destravar.
    Agora o painel tem 'Enviar pra cozinha ✓' no rascunho."""

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

    def _criar_rascunho(self) -> str:
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000110@s.whatsapp.net", "id": "msg-cr-1"},
                    "message": {"conversation": "Mesa 1"},
                }
            },
        )
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000110@s.whatsapp.net", "id": "msg-cr-2"},
                    "message": {"conversation": "uma corona"},
                }
            },
        )
        pending = self.client.get("/api/dashboard").get_json()["pending_orders"]
        self.assertEqual(len(pending), 1)
        return pending[0]["id"]

    def test_garcom_confirma_rascunho_pelo_painel(self):
        order_id = self._criar_rascunho()

        r = self.client.post(f"/api/orders/{order_id}/confirm")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["order"]["status"], "enviado_setor")
        # O rascunho saiu da lista e o item entrou na coluna do setor.
        data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(data["pending_orders"], [])
        self.assertTrue(data["columns"]["bar"])

    def test_clique_duplo_nao_confirma_duas_vezes(self):
        order_id = self._criar_rascunho()
        self.client.post(f"/api/orders/{order_id}/confirm")

        r = self.client.post(f"/api/orders/{order_id}/confirm")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json().get("reason"), "ja_confirmado")

    def test_pedido_inexistente_da_404(self):
        r = self.client.post("/api/orders/nao-existe/confirm")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
