from __future__ import annotations

import tempfile
import unittest

from mesazap.billing_service import BillingService
from mesazap.config import Settings
from mesazap.menu_service import MenuService
from mesazap.openai_interpreter import OpenAIInterpreter
from mesazap.order_service import OrderService
from mesazap.restaurant_agent import RestaurantAgent
from mesazap.storage import Database
from mesazap.table_session_service import TableSessionService


def make_environment():
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    sessions = TableSessionService(db)
    menu = MenuService(db)
    orders = OrderService(db)
    billing = BillingService(db)
    settings = Settings(
        database_path=handle.name,
        public_base_url="http://localhost:5000",
        whatsapp_phone="",
        evolution_api_url="",
        evolution_api_key="",
        evolution_instance="",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        supabase_url="",
        supabase_service_role_key="",
        admin_token="",
        dashboard_user="admin",
        dashboard_password="",
    )
    agent = RestaurantAgent(
        table_sessions=sessions,
        menu=menu,
        orders=orders,
        interpreter=OpenAIInterpreter(settings),
        billing=billing,
    )
    return db, sessions, orders, billing, agent


def restaurant_id(sessions: TableSessionService) -> str:
    return sessions.restaurant()["id"]


class BillingServiceTest(unittest.TestCase):
    def test_seed_creates_active_account(self):
        _db, sessions, _orders, billing, _agent = make_environment()
        account = billing.account_for_restaurant(restaurant_id(sessions))
        self.assertEqual(account["status"], "ativo")
        self.assertIsNotNone(account["setup_fee_paid_em"])
        self.assertAlmostEqual(float(account["preco_por_pedido"]), 1.97)
        self.assertAlmostEqual(float(account["setup_fee"]), 99.00)

    def test_mark_setup_paid_is_idempotent(self):
        db, sessions, _orders, billing, _agent = make_environment()
        rid = restaurant_id(sessions)
        first = billing.mark_setup_paid(rid)
        second = billing.mark_setup_paid(rid)
        self.assertEqual(first["setup_fee_paid_em"], second["setup_fee_paid_em"])
        setup_events = db.fetchall(
            "select id from billing_events where tipo = 'setup'"
        )
        self.assertEqual(len(setup_events), 0)

    def test_suspend_blocks_new_orders(self):
        _db, sessions, _orders, billing, agent = make_environment()
        rid = restaurant_id(sessions)
        billing.suspend(rid)

        remote = "5511999991111"
        first = agent.handle_message(remote_jid=remote, text="Mesa 12")
        self.assertEqual(first["action"], "account_inactive")

    def test_confirmed_order_creates_billing_event(self):
        _db, sessions, _orders, billing, agent = make_environment()
        remote = "5511999992222"

        agent.handle_message(remote_jid=remote, text="Mesa 12")
        agent.handle_message(remote_jid=remote, text="Me ve 2 Corona")
        agent.handle_message(remote_jid=remote, text="1")

        summary = billing.usage_summary(restaurant_id(sessions))
        self.assertEqual(summary["qtd_pedidos"], 1)
        self.assertAlmostEqual(summary["valor_pedidos"], 1.97)

    def test_record_confirmed_order_is_idempotent(self):
        db, sessions, orders, billing, agent = make_environment()
        rid = restaurant_id(sessions)
        remote = "5511999993333"

        agent.handle_message(remote_jid=remote, text="Mesa 12")
        agent.handle_message(remote_jid=remote, text="Me ve 1 Corona")
        confirmed = agent.handle_message(remote_jid=remote, text="1")
        pedido_id = confirmed["order"]["id"]

        billing.record_confirmed_order(restaurante_id=rid, pedido_id=pedido_id)
        billing.record_confirmed_order(restaurante_id=rid, pedido_id=pedido_id)

        events = db.fetchall(
            "select id from billing_events where pedido_id = ?",
            (pedido_id,),
        )
        self.assertEqual(len(events), 1)

    def test_generate_invoice_aggregates_period(self):
        _db, sessions, _orders, billing, agent = make_environment()
        rid = restaurant_id(sessions)

        agent.handle_message(remote_jid="5511999994444", text="Mesa 12")
        agent.handle_message(remote_jid="5511999994444", text="Me ve 2 Corona")
        agent.handle_message(remote_jid="5511999994444", text="1")
        agent.handle_message(remote_jid="5511999995555", text="Mesa 3")
        agent.handle_message(remote_jid="5511999995555", text="Manda 1 porcao de batata")
        agent.handle_message(remote_jid="5511999995555", text="1")

        fatura = billing.generate_invoice(rid)
        self.assertEqual(fatura["qtd_pedidos"], 2)
        self.assertAlmostEqual(float(fatura["valor_pedidos"]), 2 * 1.97)
        self.assertEqual(fatura["status"], "aberta")

        again = billing.generate_invoice(rid)
        self.assertEqual(again["id"], fatura["id"])

    def test_mark_invoice_paid_propagates_to_events(self):
        db, sessions, _orders, billing, agent = make_environment()
        rid = restaurant_id(sessions)

        agent.handle_message(remote_jid="5511999996666", text="Mesa 7")
        agent.handle_message(remote_jid="5511999996666", text="Me ve 1 Corona")
        agent.handle_message(remote_jid="5511999996666", text="1")

        fatura = billing.generate_invoice(rid)
        billing.mark_invoice_paid(fatura["id"])

        updated = db.fetchone("select status, paga_em from faturas where id = ?", (fatura["id"],))
        self.assertEqual(updated["status"], "paga")
        self.assertIsNotNone(updated["paga_em"])

        events = db.fetchall(
            "select status_cobranca from billing_events where fatura_id = ?",
            (fatura["id"],),
        )
        self.assertTrue(events)
        self.assertTrue(all(row["status_cobranca"] == "pago" for row in events))


if __name__ == "__main__":
    unittest.main()
