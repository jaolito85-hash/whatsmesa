from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from unittest import mock


class _FakeResp:
    """Resposta falsa do urlopen — evita qualquer chamada de rede no teste."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"message":"success"}'


class SDRAgenteTest(unittest.TestCase):
    """Agente SDR: leads do tráfego pago atendidos numa porta separada do garçom."""

    _KEYS = (
        "KLINK_DATABASE",
        "KLINK_DASHBOARD_PASSWORD",
        "KLINK_DEV_MODE",
        "OPENAI_API_KEY",
        "KLINK_SDR_EVOLUTION_URL",
        "KLINK_SDR_EVOLUTION_TOKEN",
        "KLINK_SDR_ALERT_NUMBER",
        "KLINK_SDR_WEBHOOK_SECRET",
    )
    ALERTA = "5544990000000"

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}
        env = {
            "KLINK_DATABASE": self._db_path,
            "KLINK_DASHBOARD_PASSWORD": "",
            "KLINK_DEV_MODE": "1",
            "OPENAI_API_KEY": "",  # sem OpenAI => agente cai no fallback
            "KLINK_SDR_EVOLUTION_URL": "http://evo.test",
            "KLINK_SDR_EVOLUTION_TOKEN": "tok-instancia",
            "KLINK_SDR_ALERT_NUMBER": self.ALERTA,
            "KLINK_SDR_WEBHOOK_SECRET": "",
        }
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from klink import config as config_module

        importlib.reload(config_module)
        import app as app_module

        importlib.reload(app_module)
        self.app_module = app_module
        self.client = app_module.app.test_client()

        # Captura os envios (sem rede). sdr_send_text usa urllib.request.urlopen.
        self.sent: list[dict] = []

        def fake_urlopen(req, timeout=None):
            self.sent.append({"url": req.full_url, "body": req.data.decode("utf-8")})
            return _FakeResp()

        self._patch = mock.patch("urllib.request.urlopen", side_effect=fake_urlopen)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _inbound(self, texto, *, jid="5544988887777@s.whatsapp.net", mid="MSG1", from_me=False, nome="Carlos"):
        return {
            "event": "MESSAGE",
            "instance": "klink-sdr",
            "data": {
                "key": {"remoteJid": jid, "fromMe": from_me, "id": mid},
                "message": {"conversation": texto},
                "messageTimestamp": "1700000000",
                "pushName": nome,
            },
        }

    def _sends_to(self, numero):
        return [s for s in self.sent if json.loads(s["body"]).get("number") == numero]

    # ---- pipeline básico (fallback, sem OpenAI) ----
    def test_lead_novo_responde_e_guarda_conversa(self):
        r = self.client.post("/webhook/sdr", json=self._inbound("oi, vi o anúncio"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "sdr_respondido")

        from klink.storage import Database

        db = Database(self._db_path)
        lead = db.sdr_get_lead("5544988887777@s.whatsapp.net")
        self.assertIsNotNone(lead)
        self.assertEqual(lead["nome"], "Carlos")
        autores = [h["autor"] for h in db.sdr_history("5544988887777@s.whatsapp.net")]
        self.assertEqual(autores, ["lead", "agente"])
        # Respondeu ao próprio lead (e não ao número de alerta).
        self.assertTrue(self._sends_to("5544988887777"))

    def test_from_me_e_duplicata_sao_ignorados(self):
        eco = self.client.post("/webhook/sdr", json=self._inbound("eco", from_me=True, mid="E1"))
        self.assertEqual(eco.get_json()["action"], "from_me_ignored")

        self.client.post("/webhook/sdr", json=self._inbound("oi", mid="D1"))
        dup = self.client.post("/webhook/sdr", json=self._inbound("oi", mid="D1"))
        self.assertEqual(dup.get_json()["action"], "duplicate_ignored")

    # ---- lead aceita o repasse => avisa o João ----
    def test_lead_aceita_dispara_alerta_uma_vez(self):
        canned = {
            "resposta": "Show! Já passei teu contato, a equipe te chama já já. 🙌",
            "lead_aceitou_contato": True,
            "nome_lead": "Bar do Zé",
            "resumo_lead": "Bar em Maringá, ~20 mesas, quer testar pra Copa.",
        }
        with mock.patch.object(self.app_module.SDRAgent, "responder", return_value=canned):
            r = self.client.post("/webhook/sdr", json=self._inbound("pode sim, quero!", mid="Q1"))
            self.assertEqual(r.get_json()["action"], "sdr_lead_qualificado")

            # Avisou o João no número de alerta, com link clicável do lead.
            alertas = self._sends_to(self.ALERTA)
            self.assertEqual(len(alertas), 1)
            corpo = json.loads(alertas[0]["body"])["text"]
            self.assertIn("Lead quente", corpo)
            self.assertIn("wa.me/5544988887777", corpo)
            self.assertIn("Maringá", corpo)

            # Segunda aceitação não deve avisar de novo (já notificado).
            r2 = self.client.post("/webhook/sdr", json=self._inbound("isso!", mid="Q2"))
            self.assertEqual(r2.get_json()["action"], "sdr_respondido")
            self.assertEqual(len(self._sends_to(self.ALERTA)), 1)

        from klink.storage import Database

        lead = Database(self._db_path).sdr_get_lead("5544988887777@s.whatsapp.net")
        self.assertEqual(lead["status"], "qualificado")
        self.assertIsNotNone(lead["notificado_em"])


if __name__ == "__main__":
    unittest.main()
