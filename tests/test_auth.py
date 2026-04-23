from __future__ import annotations

import base64
import os
import tempfile
import unittest


def _basic_auth(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class DashboardAuthTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {
            "MESAZAP_DATABASE": os.environ.get("MESAZAP_DATABASE"),
            "MESAZAP_DASHBOARD_USER": os.environ.get("MESAZAP_DASHBOARD_USER"),
            "MESAZAP_DASHBOARD_PASSWORD": os.environ.get("MESAZAP_DASHBOARD_PASSWORD"),
        }
        os.environ["MESAZAP_DATABASE"] = self._db_path
        os.environ["MESAZAP_DASHBOARD_USER"] = "joao"
        os.environ["MESAZAP_DASHBOARD_PASSWORD"] = "super-secret"

        import importlib
        from mesazap import config as config_module

        importlib.reload(config_module)
        import app as app_module

        importlib.reload(app_module)
        self.app = app_module.app
        self.client = self.app.test_client()

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_health_is_public(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_webhook_is_public(self):
        response = self.client.post(
            "/webhook/evolution",
            json={"data": {"key": {"id": "m1", "remoteJid": ""}, "message": {}}},
        )
        self.assertEqual(response.status_code, 200)

    def test_qr_redirect_is_public(self):
        response = self.client.get("/qr/unknown-token")
        self.assertEqual(response.status_code, 404)

    def test_dashboard_requires_auth(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.headers.get("WWW-Authenticate", "").startswith("Basic"))

    def test_dashboard_accepts_correct_password(self):
        response = self.client.get("/", headers=_basic_auth("joao", "super-secret"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_rejects_wrong_password(self):
        response = self.client.get("/", headers=_basic_auth("joao", "errada"))
        self.assertEqual(response.status_code, 401)

    def test_api_endpoint_requires_auth(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
