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


def make_agent() -> tuple[RestaurantAgent, OrderService]:
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
    return (
        RestaurantAgent(
            table_sessions=sessions,
            menu=menu,
            orders=orders,
            interpreter=OpenAIInterpreter(settings),
            billing=billing,
        ),
        orders,
    )


class AgentFlowTest(unittest.TestCase):
    def test_text_order_requires_confirmation_before_dashboard(self):
        agent, orders = make_agent()
        remote = "5511999999999"

        first = agent.handle_message(remote_jid=remote, text="Mesa 12")
        self.assertEqual(first["action"], "session_activated")

        draft = agent.handle_message(
            remote_jid=remote,
            text="Me ve 2 Corona e uma porcao de batata",
        )
        self.assertEqual(draft["action"], "order_draft_created")
        self.assertIn("Confirma?", draft["reply"])
        self.assertEqual(len(orders.dashboard()["columns"]["bar"]), 0)

        confirmed = agent.handle_message(remote_jid=remote, text="1")
        self.assertEqual(confirmed["action"], "order_confirmed")

        dashboard = orders.dashboard()
        self.assertEqual(len(dashboard["columns"]["bar"]), 1)
        self.assertEqual(len(dashboard["columns"]["cozinha"]), 1)

    def test_ambiguous_brahma_asks_short_question(self):
        agent, _orders = make_agent()
        remote = "5511888888888"
        agent.handle_message(remote_jid=remote, text="Mesa 8")
        result = agent.handle_message(remote_jid=remote, text="Manda uma Brahma")
        self.assertEqual(result["action"], "clarification_needed")
        self.assertIn("Brahma", result["reply"])

    def test_close_account_goes_to_cashier(self):
        agent, orders = make_agent()
        remote = "5511777777777"
        agent.handle_message(remote_jid=remote, text="Mesa 3")
        result = agent.handle_message(remote_jid=remote, text="Fecha a conta")
        self.assertEqual(result["action"], "account_requested")
        self.assertEqual(len(orders.dashboard()["columns"]["caixa"]), 1)

    def test_english_order_uses_english_reply(self):
        agent, orders = make_agent()
        remote = "447700900001"

        first = agent.handle_message(remote_jid=remote, text="Table 4")
        self.assertEqual(first["action"], "session_activated")
        self.assertEqual(first["language"], "en")
        self.assertIn("Table 4 is ready", first["reply"])

        draft = agent.handle_message(
            remote_jid=remote,
            text="Can I get two Coronas and fries please",
        )
        self.assertEqual(draft["action"], "order_draft_created")
        self.assertEqual(draft["language"], "en")
        self.assertIn("Table 4", draft["reply"])
        self.assertIn("fries", draft["reply"])
        self.assertIn("1 fries", draft["reply"])
        self.assertIn("Confirm?", draft["reply"])

        confirmed = agent.handle_message(remote_jid=remote, text="yes")
        self.assertEqual(confirmed["action"], "order_confirmed")
        self.assertEqual(confirmed["language"], "en")
        self.assertIn("the bar", confirmed["reply"])
        self.assertEqual(len(orders.dashboard()["columns"]["bar"]), 1)
        self.assertEqual(len(orders.dashboard()["columns"]["cozinha"]), 1)

    def test_spanish_order_uses_spanish_reply(self):
        agent, orders = make_agent()
        remote = "34600000000"

        agent.handle_message(remote_jid=remote, text="Mesa 5")
        draft = agent.handle_message(
            remote_jid=remote,
            text="Quiero dos Coronas y papas fritas",
        )
        self.assertEqual(draft["action"], "order_draft_created")
        self.assertEqual(draft["language"], "es")
        self.assertIn("Mesa 5", draft["reply"])
        self.assertIn("papas fritas", draft["reply"])
        self.assertIn("1 papas fritas", draft["reply"])
        self.assertIn("Confirmas?", draft["reply"])

        confirmed = agent.handle_message(remote_jid=remote, text="si")
        self.assertEqual(confirmed["action"], "order_confirmed")
        self.assertEqual(confirmed["language"], "es")
        self.assertIn("Sectores avisados", confirmed["reply"])
        self.assertEqual(len(orders.dashboard()["columns"]["bar"]), 1)
        self.assertEqual(len(orders.dashboard()["columns"]["cozinha"]), 1)


if __name__ == "__main__":
    unittest.main()
