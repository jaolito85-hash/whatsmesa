from __future__ import annotations

import tempfile
import unittest

from klink.billing_service import BillingService
from klink.config import Settings
from klink.menu_service import MenuService
from klink.openai_interpreter import OpenAIInterpreter
from klink.order_service import OrderService
from klink.restaurant_agent import RestaurantAgent
from klink.storage import Database
from klink.table_session_service import TableSessionService


def make_agent():
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    billing = BillingService(db)
    sessions = TableSessionService(db, billing=billing)
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
    orders = OrderService(db)
    agent = RestaurantAgent(
        table_sessions=sessions,
        menu=MenuService(db),
        orders=orders,
        interpreter=OpenAIInterpreter(settings),
        billing=billing,
    )
    return agent, orders, db


class ContaComTotalTest(unittest.TestCase):
    """'Fecha a conta' agora entrega o extrato pro cliente e o TOTAL pro caixa.

    Antes o caixa via só 'Fechar conta da Mesa 12' e tinha que somar a comanda
    de cabeça — exatamente onde o produto deveria brilhar e não brilhava."""

    def _pedir_e_confirmar(self, agent, remote: str):
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        agent.handle_message(remote_jid=remote, text="2 corona e uma porcao de batata")
        agent.handle_message(remote_jid=remote, text="1")

    def test_cliente_recebe_extrato_com_total(self):
        agent, _orders, _db = make_agent()
        remote = "5511900000080"
        self._pedir_e_confirmar(agent, remote)

        result = agent.handle_message(remote_jid=remote, text="fecha a conta")

        self.assertEqual(result["action"], "account_requested")
        # 2x Corona (14,00) + 1x batata (32,00) = 60,00
        self.assertIn("Conta da Mesa 5:", result["reply"])
        self.assertIn("2x Corona long neck — R$ 28,00", result["reply"])
        self.assertIn("1x Porcao de batata frita — R$ 32,00", result["reply"])
        self.assertIn("Total: R$ 60,00", result["reply"])

    def test_caixa_ve_o_total_no_ticket(self):
        agent, _orders, db = make_agent()
        remote = "5511900000081"
        self._pedir_e_confirmar(agent, remote)

        result = agent.handle_message(remote_jid=remote, text="fecha a conta")

        self.assertIn("Total R$ 60,00", result["request"]["descricao"])
        ticket = db.fetchone(
            "select descricao from solicitacoes_salao where tipo = 'fechar_conta'"
        )
        self.assertIn("Total R$ 60,00", ticket["descricao"])

    def test_conta_sem_consumo_nao_mostra_extrato(self):
        agent, _orders, _db = make_agent()
        remote = "5511900000082"
        agent.handle_message(remote_jid=remote, text="Mesa 3")

        result = agent.handle_message(remote_jid=remote, text="fecha a conta")

        self.assertEqual(result["action"], "account_requested")
        self.assertNotIn("Total:", result["reply"])
        self.assertNotIn("Total R$", result["request"]["descricao"])

    def test_item_cancelado_fica_fora_do_total(self):
        agent, orders, db = make_agent()
        remote = "5511900000083"
        self._pedir_e_confirmar(agent, remote)
        item = db.fetchone(
            "select i.id from pedido_itens i where i.nome_snapshot = 'Porcao de batata frita'"
        )
        orders.update_item_status(item["id"], "cancelado")

        result = agent.handle_message(remote_jid=remote, text="fecha a conta")

        self.assertIn("Total: R$ 28,00", result["reply"])
        self.assertNotIn("batata", result["reply"])

    def test_comanda_da_equipe_traz_o_total(self):
        def team_message_for(result):
            from app import team_message_for as fn

            return fn(result)

        agent, _orders, _db = make_agent()
        remote = "5511900000084"
        self._pedir_e_confirmar(agent, remote)
        result = agent.handle_message(remote_jid=remote, text="fecha a conta")

        text = team_message_for(result)
        self.assertIn("💰", text)
        self.assertIn("Total R$ 60,00", text)


if __name__ == "__main__":
    unittest.main()
