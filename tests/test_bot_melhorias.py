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
    agent = RestaurantAgent(
        table_sessions=sessions,
        menu=MenuService(db),
        orders=OrderService(db),
        interpreter=OpenAIInterpreter(settings),
        billing=billing,
    )
    return agent, db


class CardapioPorMensagemTest(unittest.TestCase):
    """'Qual o cardápio?' respondia 'chamei um atendente' — o cliente não
    tinha cardápio nem preço em lugar nenhum. Agora o bot responde a lista."""

    def test_cardapio_responde_lista_com_precos(self):
        agent, _db = make_agent()
        remote = "5511900000120"
        agent.handle_message(remote_jid=remote, text="Mesa 1")

        result = agent.handle_message(remote_jid=remote, text="qual o cardápio?")

        self.assertEqual(result["action"], "menu_sent")
        self.assertIn("Nosso cardápio", result["reply"])
        self.assertIn("Picanha acebolada — R$ 54,00", result["reply"])
        self.assertIn("Brahma 600ml — R$ 13,00", result["reply"])

    def test_menu_em_ingles_tambem_funciona(self):
        agent, _db = make_agent()
        remote = "5511900000121"
        agent.handle_message(remote_jid=remote, text="Mesa 1")

        result = agent.handle_message(remote_jid=remote, text="can I see the menu please?")

        self.assertEqual(result["action"], "menu_sent")

    def test_item_indisponivel_fica_fora_do_cardapio(self):
        agent, db = make_agent()
        db.execute("update produtos set disponivel = 0 where nome = 'Pudim'")
        remote = "5511900000122"
        agent.handle_message(remote_jid=remote, text="Mesa 1")

        result = agent.handle_message(remote_jid=remote, text="cardapio")

        self.assertNotIn("Pudim", result["reply"])


class TetoAntiTroteTest(unittest.TestCase):
    """'Manda 100 picanhas' não entra mais direto na fila da cozinha."""

    def test_quantidade_alta_chama_atendente_em_vez_de_lancar(self):
        agent, db = make_agent()
        remote = "5511900000123"
        agent.handle_message(remote_jid=remote, text="Mesa 2")

        result = agent.handle_message(remote_jid=remote, text="100 picanha")

        self.assertEqual(result["action"], "quantity_too_big")
        pedidos = db.fetchall("select id from pedidos")
        self.assertEqual(pedidos, [], "não pode criar rascunho de pedido")
        chamado = db.fetchone(
            "select descricao from solicitacoes_salao order by criada_em desc limit 1"
        )
        self.assertIn("quantidade alta", chamado["descricao"])

    def test_quantidade_normal_continua_passando(self):
        agent, _db = make_agent()
        remote = "5511900000124"
        agent.handle_message(remote_jid=remote, text="Mesa 2")

        result = agent.handle_message(remote_jid=remote, text="10 corona")

        self.assertEqual(result["action"], "order_draft_created")


class TextoHonestoTest(unittest.TestCase):
    def test_confirmacao_orienta_chamar_atendente_se_demorar(self):
        agent, _db = make_agent()
        remote = "5511900000125"
        agent.handle_message(remote_jid=remote, text="Mesa 3")
        agent.handle_message(remote_jid=remote, text="uma corona")

        result = agent.handle_message(remote_jid=remote, text="1")

        self.assertEqual(result["action"], "order_confirmed")
        self.assertIn("Se demorar", result["reply"])


if __name__ == "__main__":
    unittest.main()
