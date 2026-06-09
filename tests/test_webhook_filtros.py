from __future__ import annotations

import importlib
import os
import tempfile
import unittest


def _reload_app(env: dict[str, str | None]):
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    from klink import config as config_module

    importlib.reload(config_module)
    import app as app_module

    importlib.reload(app_module)
    return app_module.app


def _payload(
    *,
    text: str = "Mesa 1",
    remote_jid: str = "5511999999999@s.whatsapp.net",
    message_id: str = "msg-filtros-1",
    from_me: bool | None = None,
    event: str | None = None,
) -> dict:
    payload: dict = {
        "data": {
            "key": {"remoteJid": remote_jid, "id": message_id},
            "message": {"conversation": text},
        }
    }
    if from_me is not None:
        payload["data"]["key"]["fromMe"] = from_me
    if event is not None:
        payload["event"] = event
    return payload


class WebhookFiltrosTest(unittest.TestCase):
    """Filtros anti-loop do webhook: fromMe, eventos que não são mensagem e grupos.

    Sem o filtro de fromMe, a resposta do bot ecoada pela Evolution volta como se
    fosse o cliente falando e o bot responde a si mesmo em loop infinito — o
    cenário clássico de banimento do número.
    """

    _KEYS = ("KLINK_DATABASE", "KLINK_DASHBOARD_PASSWORD", "KLINK_WEBHOOK_SECRET", "KLINK_DEV_MODE")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}
        app = _reload_app(
            {
                "KLINK_DATABASE": self._db_path,
                "KLINK_DASHBOARD_PASSWORD": "",
                "KLINK_WEBHOOK_SECRET": None,
                "KLINK_DEV_MODE": None,
            }
        )
        self.client = app.test_client()

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ---- fromMe: mensagem do próprio bot nunca é processada ----
    def test_from_me_e_descartada(self):
        r = self.client.post("/webhook", json=_payload(from_me=True))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "from_me_ignored")

    def test_from_me_nao_abre_sessao(self):
        self.client.post("/webhook", json=_payload(text="Mesa 3", from_me=True))
        r = self.client.get("/health")
        self.assertEqual(r.get_json()["sessions"]["active"], 0)

    def test_from_me_false_processa_normalmente(self):
        r = self.client.post("/webhook", json=_payload(from_me=False))
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.get_json()["action"], "from_me_ignored")

    # ---- eventos que não são mensagem recebida ----
    def test_evento_de_conexao_vira_registro_de_estado(self):
        # connection.update não é descartado: ele alimenta o selo honesto de
        # conexão (ver test_conexao_whatsapp.py). Mas nunca vira resposta.
        r = self.client.post("/webhook", json=_payload(event="connection.update"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "connection_state_recorded")

    def test_evento_de_presenca_e_descartado(self):
        r = self.client.post("/webhook", json=_payload(event="presence.update"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "event_ignored")

    def test_evento_qrcode_e_descartado(self):
        r = self.client.post("/webhook", json=_payload(event="QRCODE_UPDATED"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "event_ignored")

    def test_messages_upsert_maiusculo_e_processado(self):
        # Evolution v1 manda MESSAGES_UPSERT; v2 manda messages.upsert.
        r = self.client.post("/webhook", json=_payload(event="MESSAGES_UPSERT"))
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.get_json()["action"], "event_ignored")

    def test_sem_campo_event_e_processado(self):
        # Simulador e testes não mandam "event": comportamento atual preservado.
        r = self.client.post("/webhook", json=_payload())
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.get_json()["action"], "event_ignored")

    # ---- grupos e broadcast não são mesa de cliente ----
    def test_mensagem_de_grupo_e_descartada(self):
        r = self.client.post(
            "/webhook",
            json=_payload(remote_jid="120363025463829@g.us"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "group_ignored")

    def test_status_broadcast_e_descartado(self):
        r = self.client.post(
            "/webhook",
            json=_payload(remote_jid="status@broadcast"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "group_ignored")

    def test_lista_de_transmissao_e_descartada(self):
        r = self.client.post(
            "/webhook",
            json=_payload(remote_jid="123456789@broadcast"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "group_ignored")

    def test_canal_newsletter_e_descartado(self):
        r = self.client.post(
            "/webhook",
            json=_payload(remote_jid="120363166555@newsletter"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "group_ignored")


if __name__ == "__main__":
    unittest.main()
