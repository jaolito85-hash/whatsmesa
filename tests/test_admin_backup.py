from __future__ import annotations

import importlib
import os
import sqlite3
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


class AdminBackupTest(unittest.TestCase):
    """Rota /admin/backup: cópia do banco fora da VPS em um comando.

    Se a VPS morrer, sem cópia externa o restaurante perde cardápio, comandas
    e faturamento — irrecuperável. Esta rota é o caminho mais simples de
    backup externo (curl do computador do fundador)."""

    _KEYS = ("KLINK_DATABASE", "KLINK_ADMIN_TOKEN", "KLINK_DEV_MODE", "KLINK_DASHBOARD_PASSWORD")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {key: os.environ.get(key) for key in self._KEYS}

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self, *, admin_token: str | None):
        app = _reload_app(
            {
                "KLINK_DATABASE": self._db_path,
                "KLINK_DASHBOARD_PASSWORD": "",
                "KLINK_ADMIN_TOKEN": admin_token,
                "KLINK_DEV_MODE": None,
            }
        )
        return app.test_client()

    def test_sem_token_nega(self):
        client = self._client(admin_token="segredo-bk")
        r = client.get("/admin/backup")
        self.assertEqual(r.status_code, 401)

    def test_sem_token_configurado_nega(self):
        client = self._client(admin_token=None)
        r = client.get("/admin/backup")
        self.assertEqual(r.status_code, 403)

    def test_download_devolve_banco_sqlite_valido(self):
        client = self._client(admin_token="segredo-bk")
        r = client.get("/admin/backup", headers={"X-Admin-Token": "segredo-bk"})

        self.assertEqual(r.status_code, 200)
        self.assertIn("klink-backup-", r.headers["Content-Disposition"])
        # Todo arquivo SQLite começa com esta assinatura.
        self.assertTrue(r.data.startswith(b"SQLite format 3"))

        # O backup restaura de verdade: salvo em disco, tem os dados da demo.
        restored = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        restored.write(r.data)
        restored.close()
        try:
            conn = sqlite3.connect(restored.name)
            mesas = conn.execute("select count(*) from mesas").fetchone()[0]
            produtos = conn.execute("select count(*) from produtos").fetchone()[0]
            conn.close()
            self.assertGreaterEqual(mesas, 12)
            self.assertGreaterEqual(produtos, 10)
        finally:
            os.unlink(restored.name)


if __name__ == "__main__":
    unittest.main()
