from __future__ import annotations

import importlib
import os
import tempfile
import unittest


def _reload_app(env: dict[str, str | None]):
    """Recarrega config + app com as variaveis de ambiente desejadas."""
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


class AdminAuthTest(unittest.TestCase):
    # Chaves de ambiente que cada teste manipula e que precisam ser restauradas.
    _KEYS = (
        "KLINK_DATABASE",
        "KLINK_ADMIN_TOKEN",
        "KLINK_DEV_MODE",
        "KLINK_DASHBOARD_PASSWORD",
    )

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {key: os.environ.get(key) for key in self._KEYS}
        # Dashboard sem senha => before_request de auth do painel fica desligado,
        # isolando o comportamento de require_admin nas rotas /admin/*.
        os.environ["KLINK_DATABASE"] = self._db_path
        os.environ["KLINK_DASHBOARD_PASSWORD"] = ""

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self, *, admin_token: str | None, dev_mode: str | None):
        app = _reload_app(
            {
                "KLINK_DATABASE": self._db_path,
                "KLINK_DASHBOARD_PASSWORD": "",
                "KLINK_ADMIN_TOKEN": admin_token,
                "KLINK_DEV_MODE": dev_mode,
            }
        )
        return app.test_client()

    def test_sem_token_e_sem_dev_mode_nega_acesso(self):
        # Achado critico 3: token vazio em producao NAO pode liberar /admin/*.
        client = self._client(admin_token=None, dev_mode=None)
        response = client.post("/admin/billing/setup-paid", json={})
        self.assertEqual(response.status_code, 403)

    def test_sem_token_mas_dev_mode_libera(self):
        # Em desenvolvimento explicito, a conveniencia de rodar sem token continua.
        client = self._client(admin_token=None, dev_mode="1")
        response = client.post("/admin/billing/setup-paid", json={})
        self.assertEqual(response.status_code, 200)

    def test_com_token_e_header_correto_aceita(self):
        client = self._client(admin_token="segredo-123", dev_mode=None)
        response = client.post(
            "/admin/billing/setup-paid",
            json={},
            headers={"X-Admin-Token": "segredo-123"},
        )
        self.assertEqual(response.status_code, 200)

    def test_com_token_e_header_errado_rejeita(self):
        # Achado critico 2: comparacao segura ainda rejeita token incorreto.
        client = self._client(admin_token="segredo-123", dev_mode=None)
        response = client.post(
            "/admin/billing/setup-paid",
            json={},
            headers={"X-Admin-Token": "errado"},
        )
        self.assertEqual(response.status_code, 401)

    def test_com_token_e_sem_header_rejeita(self):
        client = self._client(admin_token="segredo-123", dev_mode=None)
        response = client.post("/admin/billing/setup-paid", json={})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
