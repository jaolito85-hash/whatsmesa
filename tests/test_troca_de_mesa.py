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
    return agent, sessions, db


class TrocaDeMesaTest(unittest.TestCase):
    """Citar outro número de mesa NO MEIO de uma frase não pode mais fechar a
    conta atual em silêncio (pai na mesa 5 perguntando da mesa 7 = conta da
    mesa 5 fechada, mesa livre no painel e nova cobrança)."""

    def test_mencao_no_meio_da_frase_nao_troca_de_mesa(self):
        agent, sessions, db = make_agent()
        remote = "5511900000070"
        agent.handle_message(remote_jid=remote, text="Mesa 5")

        agent.handle_message(remote_jid=remote, text="a mesa 7 ta livre pros meus amigos?")

        session = sessions.active_session_for_whatsapp(remote)
        self.assertEqual(session["mesa_numero"], 5, "a sessão deve continuar na mesa 5")
        cobrancas = db.fetchall("select id from billing_events where tipo = 'mesa_aberta'")
        self.assertEqual(len(cobrancas), 1, "não pode gerar cobrança nova")

    def test_pedido_citando_mesa_nao_troca(self):
        agent, sessions, _db = make_agent()
        remote = "5511900000071"
        agent.handle_message(remote_jid=remote, text="Mesa 5")

        agent.handle_message(remote_jid=remote, text="leva um suco pra mesa 7 por favor")

        session = sessions.active_session_for_whatsapp(remote)
        self.assertEqual(session["mesa_numero"], 5)

    def test_intro_explicita_continua_trocando(self):
        # Escanear o QR de outra mesa (texto "Mesa 7" sozinho) é troca legítima.
        agent, sessions, _db = make_agent()
        remote = "5511900000072"
        agent.handle_message(remote_jid=remote, text="Mesa 5")

        result = agent.handle_message(remote_jid=remote, text="Mesa 7")

        self.assertEqual(result["action"], "session_activated")
        session = sessions.active_session_for_whatsapp(remote)
        self.assertEqual(session["mesa_numero"], 7)

    def test_primeiro_contato_com_frase_completa_ainda_abre_mesa(self):
        # Sem sessão ativa, "estou na mesa 3" continua abrindo a mesa 3.
        agent, sessions, _db = make_agent()
        remote = "5511900000073"

        agent.handle_message(remote_jid=remote, text="oi, estou na mesa 3")

        session = sessions.active_session_for_whatsapp(remote)
        self.assertIsNotNone(session)
        self.assertEqual(session["mesa_numero"], 3)


if __name__ == "__main__":
    unittest.main()
