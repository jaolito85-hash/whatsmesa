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


PAYLOAD = {
    "data": {
        "key": {"remoteJid": "5511999999999@s.whatsapp.net", "id": "msg-1"},
        "message": {"conversation": "oi"},
    }
}


class WebhookSecurityTest(unittest.TestCase):
    _KEYS = (
        "KLINK_DATABASE",
        "KLINK_WEBHOOK_SECRET",
        "KLINK_DASHBOARD_PASSWORD",
        "KLINK_DEV_MODE",
    )

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self, *, secret: str | None = None, dev_mode: str | None = None):
        app = _reload_app(
            {
                "KLINK_DATABASE": self._db_path,
                "KLINK_DASHBOARD_PASSWORD": "",
                "KLINK_WEBHOOK_SECRET": secret,
                "KLINK_DEV_MODE": dev_mode,
            }
        )
        return app.test_client()

    # ---- webhook sem segredo configurado: comportamento aberto (dev) ----
    def test_sem_segredo_aceita_webhook(self):
        client = self._client(secret=None)
        r = client.post("/webhook", json=PAYLOAD)
        self.assertEqual(r.status_code, 200)

    # ---- com segredo: exige o token ----
    def test_com_segredo_sem_token_rejeita(self):
        client = self._client(secret="s3gr3do")
        r = client.post("/webhook", json=PAYLOAD)
        self.assertEqual(r.status_code, 403)

    def test_com_segredo_no_path_aceita(self):
        client = self._client(secret="s3gr3do")
        r = client.post("/webhook/evolution/s3gr3do", json=PAYLOAD)
        self.assertEqual(r.status_code, 200)

    def test_com_segredo_na_query_aceita(self):
        client = self._client(secret="s3gr3do")
        r = client.post("/webhook?token=s3gr3do", json=PAYLOAD)
        self.assertEqual(r.status_code, 200)

    def test_com_segredo_no_header_aceita(self):
        client = self._client(secret="s3gr3do")
        r = client.post("/webhook", json=PAYLOAD, headers={"X-Webhook-Token": "s3gr3do"})
        self.assertEqual(r.status_code, 200)

    def test_com_segredo_token_errado_rejeita(self):
        client = self._client(secret="s3gr3do")
        r = client.post("/webhook/evolution/errado", json=PAYLOAD)
        self.assertEqual(r.status_code, 403)


class DemoEndpointTest(unittest.TestCase):
    _KEYS = ("KLINK_DATABASE", "KLINK_DASHBOARD_PASSWORD", "KLINK_DEV_MODE")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self, *, dev_mode: str | None):
        app = _reload_app(
            {
                "KLINK_DATABASE": self._db_path,
                "KLINK_DASHBOARD_PASSWORD": "",
                "KLINK_DEV_MODE": dev_mode,
            }
        )
        return app.test_client()

    def test_demo_bloqueado_em_producao(self):
        client = self._client(dev_mode=None)
        r = client.post("/api/demo/message", json=PAYLOAD)
        self.assertEqual(r.status_code, 403)

    def test_demo_liberado_em_dev(self):
        client = self._client(dev_mode="1")
        r = client.post("/api/demo/message", json=PAYLOAD)
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
