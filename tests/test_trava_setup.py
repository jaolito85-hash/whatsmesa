from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from klink.billing_service import BillingService, current_period
from klink.storage import Database, utc_now


class TravaSetupTest(unittest.TestCase):
    """A trava dos R$ 147: cliente real só usa o bot depois do setup pago.

    A conta da demo nasce 'ativa' para o teste funcionar de primeira, mas ao
    cadastrar o nome real (onboarding) ela volta para 'aguardando_setup' — e
    só o /admin/billing/setup-paid (após o Pix) reativa, registrando o evento
    que entra na primeira fatura."""

    _KEYS = ("KLINK_DATABASE", "KLINK_DASHBOARD_PASSWORD", "KLINK_WEBHOOK_SECRET", "KLINK_DEV_MODE", "KLINK_ADMIN_TOKEN")

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
            "KLINK_ADMIN_TOKEN": "token-teste",
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
                    "key": {"remoteJid": "5511900000100@s.whatsapp.net", "id": message_id},
                    "message": {"conversation": text},
                }
            },
        )

    def test_cadastrar_nome_real_trava_a_conta(self):
        self.client.post("/api/restaurant", json={"nome": "Boteco Central"})
        r = self._webhook("Mesa 1", "msg-ts-1")
        self.assertEqual(r.get_json()["action"], "account_inactive")

    def test_setup_pago_destrava_e_registra_o_evento(self):
        self.client.post("/api/restaurant", json={"nome": "Boteco Central"})
        self.client.post(
            "/admin/billing/setup-paid",
            json={},
            headers={"X-Admin-Token": "token-teste"},
        )
        r = self._webhook("Mesa 1", "msg-ts-2")
        self.assertEqual(r.get_json()["action"], "session_activated")
        # O evento de setup agora existe e entra na primeira fatura.
        db = Database(self._db_path)
        evento = db.fetchone("select valor from billing_events where tipo = 'setup'")
        self.assertIsNotNone(evento)
        self.assertAlmostEqual(float(evento["valor"]), 147.00)

    def test_renomear_cliente_que_ja_pagou_nao_trava_de_novo(self):
        self.client.post("/api/restaurant", json={"nome": "Boteco Central"})
        self.client.post(
            "/admin/billing/setup-paid",
            json={},
            headers={"X-Admin-Token": "token-teste"},
        )
        # Renomear depois de pago não pode bloquear o cliente.
        self.client.post("/api/restaurant", json={"nome": "Boteco Central 2"})
        r = self._webhook("Mesa 1", "msg-ts-3")
        self.assertEqual(r.get_json()["action"], "session_activated")

    def test_demo_continua_funcionando_sem_setup(self):
        # Sem cadastrar nome real, a demo segue ativa (teste de primeira).
        r = self._webhook("Mesa 1", "msg-ts-4")
        self.assertEqual(r.get_json()["action"], "session_activated")

    def test_mesas_da_fase_demo_nao_entram_na_primeira_fatura(self):
        # O fundador testa com 2 mesas na demo; isso é cortesia, não cobrança.
        self._webhook("Mesa 1", "msg-ts-5")
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000101@s.whatsapp.net", "id": "msg-ts-6"},
                    "message": {"conversation": "Mesa 2"},
                }
            },
        )
        # Onboarding do cliente real + setup pago.
        self.client.post("/api/restaurant", json={"nome": "Boteco Central"})
        self.client.post(
            "/admin/billing/setup-paid",
            json={},
            headers={"X-Admin-Token": "token-teste"},
        )
        # Primeira mesa REAL do cliente.
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000102@s.whatsapp.net", "id": "msg-ts-7"},
                    "message": {"conversation": "Mesa 3"},
                }
            },
        )

        r = self.client.post(
            "/admin/billing/generate-invoice",
            json={},
            headers={"X-Admin-Token": "token-teste"},
        )
        fatura = r.get_json()

        # Só a 1 mesa real entra; as 2 da demo ficam de fora. O setup não entra
        # na fatura mensal porque já foi pago à parte (evento nasce 'pago').
        self.assertEqual(fatura["qtd_pedidos"], 1)
        self.assertAlmostEqual(float(fatura["valor_pedidos"]), 3.97)
        self.assertAlmostEqual(float(fatura["valor_total"]), 3.97)

    def test_fatura_com_periodo_invalido_da_400(self):
        r = self.client.post(
            "/admin/billing/generate-invoice",
            json={"periodo": "2026-1"},
            headers={"X-Admin-Token": "token-teste"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["reason"], "periodo_invalido")


class FaturaSemBuracosTest(unittest.TestCase):
    """Eventos pendentes de meses anteriores entram na próxima fatura em vez
    de ficarem 'pendente' para sempre (dinheiro que nunca era cobrado)."""

    def test_fatura_varre_pendencias_de_meses_anteriores(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        db = Database(handle.name)
        db.init_schema()
        db.seed_demo()
        billing = BillingService(db)
        rid = db.fetchone("select id from restaurantes")["id"]
        account = billing.account_for_restaurant(rid)

        # Evento "esquecido" de um mês passado (depois da fatura daquele mês).
        db.execute(
            """
            insert into billing_events (
               id, billing_account_id, tipo, sessao_mesa_id, valor, moeda,
               periodo_ano_mes, status_cobranca, criado_em
            ) values ('evt-velho', ?, 'mesa_aberta', NULL, 3.97, 'BRL', '2020-01', 'pendente', ?)
            """,
            (account["id"], utc_now()),
        )
        db.execute(
            """
            insert into billing_events (
               id, billing_account_id, tipo, sessao_mesa_id, valor, moeda,
               periodo_ano_mes, status_cobranca, criado_em
            ) values ('evt-atual', ?, 'mesa_aberta', NULL, 3.97, 'BRL', ?, 'pendente', ?)
            """,
            (account["id"], current_period(), utc_now()),
        )

        fatura = billing.generate_invoice(rid)

        self.assertEqual(fatura["qtd_pedidos"], 2)
        velho = db.fetchone("select status_cobranca, fatura_id from billing_events where id = 'evt-velho'")
        self.assertEqual(velho["status_cobranca"], "faturado")
        self.assertEqual(velho["fatura_id"], fatura["id"])


if __name__ == "__main__":
    unittest.main()
