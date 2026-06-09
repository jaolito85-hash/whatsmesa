from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from unittest import mock


def team_message_for(result):
    # Import adiado: o módulo app instancia o Flask na importação e exige env de
    # produção fora do pytest — na coleta dos testes isso quebraria.
    from app import team_message_for as fn

    return fn(result)


class TeamMessageForTest(unittest.TestCase):
    """A comanda de texto enviada ao WhatsApp da equipe (caminho sem tablet)."""

    def _result_pedido(self) -> dict:
        return {
            "action": "order_confirmed",
            "session": {"mesa_numero": 12},
            "order": {
                "items": [
                    {
                        "quantidade": 2,
                        "nome_snapshot": "Picanha acebolada",
                        "observacoes": "sem cebola",
                        "preco_unitario_snapshot": 54.0,
                    },
                    {
                        "quantidade": 1,
                        "nome_snapshot": "Brahma 600ml",
                        "observacoes": "",
                        "preco_unitario_snapshot": 13.0,
                    },
                ]
            },
        }

    def test_pedido_confirmado_vira_comanda(self):
        text = team_message_for(self._result_pedido())
        self.assertIn("MESA 12", text)
        self.assertIn("2x Picanha acebolada (sem cebola)", text)
        self.assertIn("1x Brahma 600ml", text)
        self.assertIn("Total parcial: R$ 121,00", text)

    def test_item_cancelado_fica_de_fora(self):
        result = self._result_pedido()
        result["order"]["items"][0]["status"] = "cancelado"
        text = team_message_for(result)
        self.assertNotIn("Picanha", text)
        self.assertIn("Total parcial: R$ 13,00", text)

    def test_conta_solicitada(self):
        text = team_message_for(
            {"action": "account_requested", "session": {"mesa_numero": 7}}
        )
        self.assertIn("MESA 7", text)
        self.assertIn("conta", text)

    def test_chamado_de_atendimento(self):
        text = team_message_for(
            {
                "action": "service_requested",
                "session": {"mesa_numero": 3},
                "request": {"descricao": "Mesa 3: derramei a cerveja"},
            }
        )
        self.assertIn("Mesa 3: derramei a cerveja", text)

    def test_acoes_irrelevantes_nao_geram_mensagem(self):
        for action in ("need_table", "session_activated", "order_draft_created", "nothing_to_confirm"):
            self.assertIsNone(
                team_message_for({"action": action, "session": {"mesa_numero": 1}}),
                f"action={action} não deveria notificar a equipe",
            )

    def test_sem_sessao_nao_gera_mensagem(self):
        self.assertIsNone(team_message_for({"action": "order_confirmed", "session": None}))


class _FakeResponse:
    def read(self):
        return b'{"status": "ok"}'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ComandaEquipeE2ETest(unittest.TestCase):
    """Fluxo completo: cliente confirma no WhatsApp -> comanda chega no número
    da equipe cadastrado nas Configurações."""

    _KEYS = (
        "KLINK_DATABASE",
        "KLINK_DASHBOARD_PASSWORD",
        "KLINK_WEBHOOK_SECRET",
        "KLINK_DEV_MODE",
        "EVOLUTION_API_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE",
        "OPENAI_API_KEY",
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
            "OPENAI_API_KEY": None,
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

    def _webhook(self, text: str, message_id: str):
        return self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {
                        "remoteJid": "5511900000030@s.whatsapp.net",
                        "id": message_id,
                    },
                    "message": {"conversation": text},
                }
            },
        )

    def test_pedido_confirmado_chega_no_whatsapp_da_equipe(self):
        self.client.post(
            "/api/restaurant",
            json={"nome": "Bar do Zé", "whatsapp_equipe": "55 11 98888-7777"},
        )

        sends: list[dict] = []

        def fake_urlopen(request, timeout=None):
            sends.append(json.loads(request.data.decode("utf-8")))
            return _FakeResponse()

        with mock.patch("klink.whatsapp_adapter.urllib.request.urlopen", fake_urlopen):
            self._webhook("Mesa 2", "msg-ce-1")
            self._webhook("uma corona", "msg-ce-2")
            self._webhook("1", "msg-ce-3")

        team_sends = [s for s in sends if s.get("number") == "5511988887777"]
        self.assertEqual(len(team_sends), 1, f"esperava 1 comanda pra equipe, sends={sends}")
        self.assertIn("MESA 2", team_sends[0]["text"])
        self.assertIn("1x Corona long neck", team_sends[0]["text"])

    def test_sem_numero_da_equipe_nao_envia_nada_extra(self):
        sends: list[dict] = []

        def fake_urlopen(request, timeout=None):
            sends.append(json.loads(request.data.decode("utf-8")))
            return _FakeResponse()

        with mock.patch("klink.whatsapp_adapter.urllib.request.urlopen", fake_urlopen):
            self._webhook("Mesa 3", "msg-ce-4")
            self._webhook("uma corona", "msg-ce-5")
            self._webhook("1", "msg-ce-6")

        # Só as 3 respostas ao cliente — nenhuma comanda extra.
        self.assertEqual(len(sends), 3)
        for send in sends:
            self.assertEqual(send["number"], "5511900000030@s.whatsapp.net")

    def test_falha_no_envio_da_comanda_nao_quebra_resposta_ao_cliente(self):
        self.client.post(
            "/api/restaurant",
            json={"nome": "Bar do Zé", "whatsapp_equipe": "5511988887777"},
        )

        def fake_urlopen(request, timeout=None):
            body = json.loads(request.data.decode("utf-8"))
            if body.get("number") == "5511988887777":
                raise OSError("evolution fora do ar")
            return _FakeResponse()

        with mock.patch("klink.whatsapp_adapter.urllib.request.urlopen", fake_urlopen):
            self._webhook("Mesa 4", "msg-ce-7")
            self._webhook("uma corona", "msg-ce-8")
            r = self._webhook("1", "msg-ce-9")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "order_confirmed")

    def test_simulador_do_painel_nao_dispara_comanda_real(self):
        # O /api/demo/message (dev) simula o cliente, mas NÃO pode enviar
        # WhatsApp de verdade — nem comanda pra equipe, nem resposta.
        os.environ["KLINK_DEV_MODE"] = "1"
        from klink import config as config_module

        importlib.reload(config_module)
        import app as app_module

        importlib.reload(app_module)
        client = app_module.app.test_client()
        client.post(
            "/api/restaurant",
            json={"nome": "Bar do Zé", "whatsapp_equipe": "5511988887777"},
        )

        sends: list[dict] = []

        def fake_urlopen(request, timeout=None):
            sends.append(json.loads(request.data.decode("utf-8")))
            return _FakeResponse()

        def demo(text, message_id):
            return client.post(
                "/api/demo/message",
                json={"remote_jid": "5511900000031", "text": text, "message_id": message_id},
            )

        with mock.patch("klink.whatsapp_adapter.urllib.request.urlopen", fake_urlopen):
            demo("Mesa 5", "msg-demo-1")
            demo("uma corona", "msg-demo-2")
            r = demo("1", "msg-demo-3")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(sends, [], "simulador não deveria enviar WhatsApp real")

    def test_whatsapp_equipe_invalido_e_rejeitado(self):
        for invalido in ("@g.us", "abc@def.com", "http://x.com/a@g.us", "123@gus"):
            r = self.client.post(
                "/api/restaurant",
                json={"nome": "Bar do Zé", "whatsapp_equipe": invalido},
            )
            self.assertEqual(r.status_code, 400, f"{invalido!r} deveria ser rejeitado")
            self.assertEqual(r.get_json()["reason"], "whatsapp_equipe_invalido")

    def test_api_restaurant_preserva_id_de_grupo(self):
        self.client.post(
            "/api/restaurant",
            json={"nome": "Bar do Zé", "whatsapp_equipe": "120363025463829@g.us"},
        )
        import app as app_module

        restaurant = app_module.app.test_client().get("/config")
        self.assertEqual(restaurant.status_code, 200)
        self.assertIn(b"120363025463829@g.us", restaurant.data)


if __name__ == "__main__":
    unittest.main()
