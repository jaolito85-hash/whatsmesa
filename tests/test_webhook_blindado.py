from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from unittest import mock


def _payload(text: str, message_id: str, remote: str = "5511900000090@s.whatsapp.net") -> dict:
    return {
        "data": {
            "key": {"remoteJid": remote, "id": message_id},
            "message": {"conversation": text},
        }
    }


class WebhookBlindadoTest(unittest.TestCase):
    """Erro inesperado no processamento não pode deixar o cliente no vácuo.

    Antes: bug na lógica virava HTTP 500, o cliente mandava de novo e a
    reentrega era descartada como 'duplicada' — mensagem perdida PARA SEMPRE."""

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

    def test_erro_inesperado_responde_contingencia(self):
        from klink.restaurant_agent import RestaurantAgent

        with mock.patch.object(
            RestaurantAgent, "handle_message", side_effect=RuntimeError("bug surpresa")
        ):
            r = self.client.post("/webhook", json=_payload("Mesa 1", "msg-bl-1"))

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "internal_error")

    def test_apos_erro_nova_mensagem_funciona_normal(self):
        from klink.restaurant_agent import RestaurantAgent

        with mock.patch.object(
            RestaurantAgent, "handle_message", side_effect=RuntimeError("bug surpresa")
        ):
            self.client.post("/webhook", json=_payload("Mesa 1", "msg-bl-2"))

        # Mensagem NOVA (id diferente) processa normalmente depois do erro.
        r = self.client.post("/webhook", json=_payload("Mesa 1", "msg-bl-3"))
        self.assertEqual(r.get_json()["action"], "session_activated")

    def test_reentrega_da_mesma_mensagem_e_duplicada(self):
        self.client.post("/webhook", json=_payload("Mesa 2", "msg-bl-4"))
        r = self.client.post("/webhook", json=_payload("Mesa 2", "msg-bl-4"))
        self.assertEqual(r.get_json()["action"], "duplicate_ignored")

    def test_duracao_de_audio_malformada_nao_estoura(self):
        payload = {
            "data": {
                "key": {"remoteJid": "5511900000091@s.whatsapp.net", "id": "msg-bl-5"},
                "message": {
                    "audioMessage": {"url": "http://example.com/a.ogg", "seconds": "abc"}
                },
            }
        }
        r = self.client.post("/webhook", json=payload)
        # Sem OpenAI configurada a transcrição falha com resposta educada —
        # o que importa é não virar HTTP 500.
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
