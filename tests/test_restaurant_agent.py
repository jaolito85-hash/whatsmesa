from __future__ import annotations

"""
Testes para klink/restaurant_agent.py.

Complementa test_agent_flow.py — não duplica casos já cobertos lá.
Cobre: métodos auxiliares (_is_confirm, _is_alter, _is_repeat, _is_account_request,
_service_type, _join_items, _display_name, _human_sectors, _message, _is_table_intro,
_items_summary), branches de handle_message (empty text, awaiting_validation,
alter_order, service_requested, repeat, unavailable, human_called, account_inactive)
e _handle_openai_result (clarification_question, intents: repeat, close_account,
service, order-not-found, order-empty-items, unknown).
"""

import tempfile
import unittest
from typing import Any
from unittest.mock import MagicMock

from klink.billing_service import BillingService
from klink.config import Settings
from klink.menu_service import MenuService
from klink.openai_interpreter import OpenAIInterpreter
from klink.order_service import OrderService
from klink.restaurant_agent import (
    CONFIRM_WORDS,
    ALTER_WORDS,
    REPEAT_MARKERS,
    ACCOUNT_MARKERS,
    RestaurantAgent,
)
from klink.storage import Database
from klink.table_session_service import TableSessionService


# ---------------------------------------------------------------------------
# Fixture compartilhada
# ---------------------------------------------------------------------------

def make_environment(
    require_validation: bool = False,
) -> tuple[RestaurantAgent, OrderService, TableSessionService, BillingService, Database]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    billing = BillingService(db)
    sessions = TableSessionService(db, billing=billing, require_validation=require_validation)
    menu = MenuService(db)
    orders = OrderService(db)
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
    return agent, orders, sessions, billing, db


def _activate_table(agent: RestaurantAgent, remote: str, mesa: str = "Mesa 5") -> dict[str, Any]:
    result = agent.handle_message(remote_jid=remote, text=mesa)
    assert result["action"] in ("session_activated", "awaiting_validation"), result
    return result


# ---------------------------------------------------------------------------
# _is_confirm — variedade de palavras de confirmação
# ---------------------------------------------------------------------------

class IsConfirmTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_confirma_word(self):
        assert self.agent._is_confirm("confirma")

    def test_sim_word(self):
        assert self.agent._is_confirm("sim")

    def test_s_word(self):
        assert self.agent._is_confirm("s")

    def test_confirmar_word(self):
        assert self.agent._is_confirm("confirmar")

    def test_pode_mandar_phrase(self):
        assert self.agent._is_confirm("pode mandar")

    def test_fechado_word(self):
        assert self.agent._is_confirm("fechado")

    def test_yes_word(self):
        assert self.agent._is_confirm("yes")

    def test_y_word(self):
        assert self.agent._is_confirm("y")

    def test_si_word(self):
        assert self.agent._is_confirm("si")

    def test_confirmo_word(self):
        assert self.agent._is_confirm("confirmo")

    def test_go_ahead_phrase(self):
        assert self.agent._is_confirm("go ahead")

    def test_word_not_in_confirm_set(self):
        assert not self.agent._is_confirm("nao")

    def test_empty_string_not_confirm(self):
        assert not self.agent._is_confirm("")

    def test_number_2_not_confirm(self):
        assert not self.agent._is_confirm("2")

    # confirm* prefix rule
    def test_confirmed_prefix(self):
        assert self.agent._is_confirm("confirmed")

    def test_confirmation_prefix(self):
        assert self.agent._is_confirm("confirmation")


# ---------------------------------------------------------------------------
# _is_alter
# ---------------------------------------------------------------------------

class IsAlterTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_alterar_word(self):
        assert self.agent._is_alter("alterar")

    def test_2_word(self):
        assert self.agent._is_alter("2")

    def test_change_word(self):
        assert self.agent._is_alter("change")

    def test_cambiar_word(self):
        assert self.agent._is_alter("cambiar")

    def test_confirm_not_alter(self):
        assert not self.agent._is_alter("confirmar")

    def test_empty_not_alter(self):
        assert not self.agent._is_alter("")


# ---------------------------------------------------------------------------
# _is_repeat
# ---------------------------------------------------------------------------

class IsRepeatTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_outra_rodada(self):
        assert self.agent._is_repeat("outra rodada")

    def test_mais_uma_igual(self):
        assert self.agent._is_repeat("mais uma igual")

    def test_repete(self):
        assert self.agent._is_repeat("repete")

    def test_same_again_english(self):
        assert self.agent._is_repeat("same again please")

    def test_otra_ronda_spanish(self):
        assert self.agent._is_repeat("otra ronda por favor")

    def test_normal_order_not_repeat(self):
        assert not self.agent._is_repeat("me ve uma corona")

    def test_empty_not_repeat(self):
        assert not self.agent._is_repeat("")


# ---------------------------------------------------------------------------
# _is_account_request
# ---------------------------------------------------------------------------

class IsAccountRequestTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_fecha_a_conta(self):
        assert self.agent._is_account_request("fecha a conta")

    def test_pagar(self):
        assert self.agent._is_account_request("pagar")

    def test_bill_please(self):
        assert self.agent._is_account_request("bill please")

    def test_la_cuenta(self):
        assert self.agent._is_account_request("la cuenta")

    def test_normal_text_not_account(self):
        assert not self.agent._is_account_request("me ve uma corona")

    def test_empty_not_account(self):
        assert not self.agent._is_account_request("")


# ---------------------------------------------------------------------------
# _service_type
# ---------------------------------------------------------------------------

class ServiceTypeTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_limpar_returns_limpeza(self):
        assert self.agent._service_type("limpar a mesa") == "limpeza"

    def test_derramei_returns_limpeza(self):
        assert self.agent._service_type("derramei o copo") == "limpeza"

    def test_guardanapo_returns_guardanapo(self):
        assert self.agent._service_type("preciso de guardanapo") == "guardanapo"

    def test_garfo_returns_talher(self):
        assert self.agent._service_type("preciso de garfo") == "talher"

    def test_garcom_returns_chamar_garcom(self):
        assert self.agent._service_type("chama o garcom") == "chamar_garcom"

    def test_waiter_returns_chamar_garcom(self):
        assert self.agent._service_type("waiter please") == "chamar_garcom"

    def test_napkin_returns_guardanapo(self):
        assert self.agent._service_type("napkin please") == "guardanapo"

    def test_fork_returns_talher(self):
        assert self.agent._service_type("fork please") == "talher"

    def test_molho_returns_molho(self):
        assert self.agent._service_type("preciso de molho") == "molho"

    def test_limao_returns_limao(self):
        assert self.agent._service_type("quero limao") == "limao"

    def test_normal_text_returns_none(self):
        assert self.agent._service_type("me ve uma corona") is None

    def test_empty_returns_none(self):
        assert self.agent._service_type("") is None

    # _service_type usa tokens, entao a palavra deve ser separada
    def test_partial_word_not_matched(self):
        # "limpou" nao esta em SERVICE_MARKERS, portanto deve retornar None
        assert self.agent._service_type("alimpou") is None


# ---------------------------------------------------------------------------
# _join_items
# ---------------------------------------------------------------------------

class JoinItemsTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_lista_vazia_retorna_string_vazia(self):
        assert self.agent._join_items([], "pt") == ""

    def test_um_item_retorna_item(self):
        assert self.agent._join_items(["cerveja"], "pt") == "cerveja"

    def test_dois_itens_pt_usa_e(self):
        result = self.agent._join_items(["cerveja", "batata"], "pt")
        assert result == "cerveja e batata"

    def test_dois_itens_en_usa_and(self):
        result = self.agent._join_items(["beer", "fries"], "en")
        assert result == "beer and fries"

    def test_dois_itens_es_usa_y(self):
        result = self.agent._join_items(["cerveza", "papas"], "es")
        assert result == "cerveza y papas"

    def test_tres_itens_pt_virgula_e_e(self):
        result = self.agent._join_items(["a", "b", "c"], "pt")
        assert result == "a, b e c"

    def test_tres_itens_en_virgula_e_and(self):
        result = self.agent._join_items(["a", "b", "c"], "en")
        assert result == "a, b and c"

    def test_idioma_desconhecido_usa_e(self):
        result = self.agent._join_items(["a", "b"], "xx")
        assert result == "a e b"


# ---------------------------------------------------------------------------
# _display_name
# ---------------------------------------------------------------------------

class DisplayNameTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_pt_retorna_nome_sem_alterar(self):
        assert self.agent._display_name("Porcao de batata frita", "pt") == "Porcao de batata frita"

    def test_en_mapeado_retorna_nome_ingles(self):
        assert self.agent._display_name("Porcao de batata frita", "en") == "fries"

    def test_es_mapeado_retorna_nome_espanhol(self):
        assert self.agent._display_name("Porcao de batata frita", "es") == "papas fritas"

    def test_en_sem_mapeamento_retorna_original(self):
        # "Corona long neck" nao esta em DISPLAY_NAMES, deve retornar o proprio nome
        assert self.agent._display_name("Corona long neck", "en") == "Corona long neck"

    def test_agua_sem_gas_en(self):
        assert self.agent._display_name("agua sem gas", "en") == "still water"

    def test_pudim_es(self):
        assert self.agent._display_name("pudim", "es") == "pudin"


# ---------------------------------------------------------------------------
# _human_sectors
# ---------------------------------------------------------------------------

class HumanSectorsTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_bar_em_pt(self):
        assert self.agent._human_sectors(["bar"], "pt") == "o balcão"

    def test_bar_em_en(self):
        assert self.agent._human_sectors(["bar"], "en") == "the bar"

    def test_bar_em_es(self):
        assert self.agent._human_sectors(["bar"], "es") == "el bar"

    def test_cozinha_em_pt(self):
        assert self.agent._human_sectors(["cozinha"], "pt") == "a cozinha"

    def test_multiplos_setores_pt(self):
        result = self.agent._human_sectors(["bar", "cozinha"], "pt")
        assert "o balcão" in result
        assert "a cozinha" in result

    def test_setor_desconhecido_retorna_proprio_nome(self):
        result = self.agent._human_sectors(["xyz"], "pt")
        assert result == "xyz"

    def test_lista_vazia_retorna_fallback_pt(self):
        result = self.agent._human_sectors([], "pt")
        assert result == "a equipe"

    def test_lista_vazia_retorna_fallback_en(self):
        result = self.agent._human_sectors([], "en")
        assert result == "the team"

    def test_lista_vazia_retorna_fallback_es(self):
        result = self.agent._human_sectors([], "es")
        assert result == "el equipo"


# ---------------------------------------------------------------------------
# _message
# ---------------------------------------------------------------------------

class MessageTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_need_table_pt(self):
        msg = self.agent._message("need_table", "pt")
        assert "mesa" in msg.lower()

    def test_need_table_en(self):
        msg = self.agent._message("need_table", "en")
        assert "table" in msg.lower()

    def test_need_table_es(self):
        msg = self.agent._message("need_table", "es")
        assert "mesa" in msg.lower()

    def test_session_activated_substitui_table(self):
        msg = self.agent._message("session_activated", "pt", table=7)
        assert "7" in msg

    def test_order_confirmed_substitui_sectors(self):
        msg = self.agent._message("order_confirmed", "pt", sectors="o balcão")
        assert "o balcão" in msg

    def test_chave_inexistente_retorna_string_vazia(self):
        msg = self.agent._message("chave_que_nao_existe", "pt")
        assert msg == ""

    def test_idioma_inexistente_cai_no_pt(self):
        # Idioma "xx" nao existe — deve cair no "pt"
        msg = self.agent._message("need_table", "xx")
        assert "mesa" in msg.lower()


# ---------------------------------------------------------------------------
# _is_table_intro
# ---------------------------------------------------------------------------

class IsTableIntroTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_mesa_numero_simples(self):
        assert self.agent._is_table_intro("Mesa 5")

    def test_table_numero_ingles(self):
        assert self.agent._is_table_intro("Table 12")

    def test_mesa_e_nome_curto(self):
        # "Mesa 5 ok" tem 3 tokens — deve passar (<=3)
        assert self.agent._is_table_intro("Mesa 5 ok")

    def test_frase_longa_nao_e_intro(self):
        # Mais de 3 tokens — nao deve ser considerada intro de mesa
        assert not self.agent._is_table_intro("Me ve uma cerveja na mesa 5")

    def test_texto_sem_mesa_nao_e_intro(self):
        assert not self.agent._is_table_intro("Quero uma cerveja")

    def test_texto_vazio_nao_e_intro(self):
        assert not self.agent._is_table_intro("")


# ---------------------------------------------------------------------------
# _items_summary — fallback nome_snapshot
# ---------------------------------------------------------------------------

class ItemsSummaryTest(unittest.TestCase):
    def setUp(self):
        agent, *_ = make_environment()
        self.agent = agent

    def test_usa_nome_quando_disponivel(self):
        items = [{"quantidade": 2, "nome": "Corona long neck"}]
        result = self.agent._items_summary(items, "pt")
        assert "Corona long neck" in result
        assert "2" in result

    def test_usa_nome_snapshot_quando_nome_ausente(self):
        items = [{"quantidade": 1, "nome_snapshot": "Porcao de batata frita"}]
        result = self.agent._items_summary(items, "pt")
        assert "Porcao de batata frita" in result

    def test_lista_vazia_retorna_string_vazia(self):
        result = self.agent._items_summary([], "pt")
        assert result == ""

    def test_display_name_aplicado_en(self):
        items = [{"quantidade": 1, "nome": "Porcao de batata frita"}]
        result = self.agent._items_summary(items, "en")
        assert "fries" in result

    def test_multiplos_itens_unidos(self):
        items = [
            {"quantidade": 2, "nome": "Corona long neck"},
            {"quantidade": 1, "nome": "Porcao de batata frita"},
        ]
        result = self.agent._items_summary(items, "pt")
        assert "Corona long neck" in result
        assert "Porcao de batata frita" in result


# ---------------------------------------------------------------------------
# handle_message — texto vazio / sem sessão
# ---------------------------------------------------------------------------

class HandleMessageSemSessaoTest(unittest.TestCase):
    def test_texto_vazio_sem_sessao_retorna_need_table(self):
        agent, *_ = make_environment()
        result = agent.handle_message(remote_jid="5511000000001", text="")
        assert result["action"] == "need_table"
        assert result["session"] is None

    def test_texto_whitespace_sem_sessao_retorna_need_table(self):
        agent, *_ = make_environment()
        result = agent.handle_message(remote_jid="5511000000002", text="   ")
        assert result["action"] == "need_table"

    def test_texto_aleatorio_sem_sessao_retorna_need_table(self):
        agent, *_ = make_environment()
        result = agent.handle_message(remote_jid="5511000000003", text="bom dia")
        assert result["action"] == "need_table"

    def test_reply_need_table_em_portugues(self):
        agent, *_ = make_environment()
        result = agent.handle_message(remote_jid="5511000000004", text="")
        assert "mesa" in result["reply"].lower()


# ---------------------------------------------------------------------------
# handle_message — conta suspensa (account_inactive)
# ---------------------------------------------------------------------------

class HandleMessageAccountInactiveTest(unittest.TestCase):
    def test_conta_suspensa_retorna_account_inactive(self):
        agent, orders, sessions, billing, db = make_environment()
        rid = sessions.restaurant()["id"]
        billing.suspend(rid)
        result = agent.handle_message(remote_jid="5511000000010", text="Mesa 5")
        assert result["action"] == "account_inactive"
        assert result["session"] is None

    def test_reply_account_inactive_pt(self):
        agent, orders, sessions, billing, db = make_environment()
        rid = sessions.restaurant()["id"]
        billing.suspend(rid)
        result = agent.handle_message(remote_jid="5511000000011", text="Mesa 5")
        # Deve conter orientacao para chamar atendente
        assert "atendente" in result["reply"].lower() or "ajust" in result["reply"].lower()


# ---------------------------------------------------------------------------
# handle_message — sessao_pendente (awaiting_validation)
# ---------------------------------------------------------------------------

class HandleMessageAwaitingValidationTest(unittest.TestCase):
    def test_ativar_mesa_com_require_validation_retorna_awaiting(self):
        agent, orders, sessions, billing, db = make_environment(require_validation=True)
        result = agent.handle_message(remote_jid="5511000000020", text="Mesa 3")
        assert result["action"] == "awaiting_validation"

    def test_nova_mensagem_com_sessao_pendente_retorna_awaiting(self):
        agent, orders, sessions, billing, db = make_environment(require_validation=True)
        remote = "5511000000021"
        agent.handle_message(remote_jid=remote, text="Mesa 3")
        # Segunda mensagem com sessao ainda pendente
        result = agent.handle_message(remote_jid=remote, text="quero uma corona")
        assert result["action"] == "awaiting_validation"

    def test_reply_awaiting_contem_numero_da_mesa(self):
        agent, orders, sessions, billing, db = make_environment(require_validation=True)
        result = agent.handle_message(remote_jid="5511000000022", text="Mesa 7")
        assert "7" in result["reply"]


# ---------------------------------------------------------------------------
# handle_message — confirmar sem pedido pendente
# ---------------------------------------------------------------------------

class HandleMessageConfirmSemPedidoTest(unittest.TestCase):
    def test_confirmar_sem_pedido_pendente_retorna_nothing_to_confirm(self):
        agent, *_ = make_environment()
        remote = "5511000000030"
        _activate_table(agent, remote, "Mesa 6")
        result = agent.handle_message(remote_jid=remote, text="sim")
        assert result["action"] == "nothing_to_confirm"

    def test_reply_nothing_to_confirm_pt(self):
        agent, *_ = make_environment()
        remote = "5511000000031"
        _activate_table(agent, remote, "Mesa 6")
        result = agent.handle_message(remote_jid=remote, text="1")
        assert "pedido" in result["reply"].lower()


# ---------------------------------------------------------------------------
# handle_message — alter_order
# ---------------------------------------------------------------------------

class HandleMessageAlterOrderTest(unittest.TestCase):
    def test_alterar_com_pedido_pendente_retorna_alter_order(self):
        agent, *_ = make_environment()
        remote = "5511000000040"
        _activate_table(agent, remote, "Mesa 9")
        agent.handle_message(remote_jid=remote, text="quero uma corona")
        result = agent.handle_message(remote_jid=remote, text="2")
        assert result["action"] == "alter_order"

    def test_alterar_sem_pedido_tambem_retorna_alter_order(self):
        # O branch de alter nao verifica se há pedido pendente
        agent, *_ = make_environment()
        remote = "5511000000041"
        _activate_table(agent, remote, "Mesa 9")
        result = agent.handle_message(remote_jid=remote, text="alterar")
        assert result["action"] == "alter_order"

    def test_reply_alter_order_pt(self):
        agent, *_ = make_environment()
        remote = "5511000000042"
        _activate_table(agent, remote, "Mesa 9")
        result = agent.handle_message(remote_jid=remote, text="alterar")
        assert "alterar" in result["reply"].lower() or "mudar" in result["reply"].lower() or "diga" in result["reply"].lower()


# ---------------------------------------------------------------------------
# handle_message — service_requested
# ---------------------------------------------------------------------------

class HandleMessageServiceRequestedTest(unittest.TestCase):
    def test_limpeza_retorna_service_requested(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000050"
        _activate_table(agent, remote, "Mesa 2")
        result = agent.handle_message(remote_jid=remote, text="pode limpar a mesa")
        assert result["action"] == "service_requested"

    def test_service_request_aparece_no_dashboard_salao(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000051"
        _activate_table(agent, remote, "Mesa 2")
        agent.handle_message(remote_jid=remote, text="preciso de guardanapo")
        dash = orders.dashboard()
        assert len(dash["columns"]["salao"]) >= 1

    def test_chamar_garcom_retorna_service_requested(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000052"
        _activate_table(agent, remote, "Mesa 2")
        result = agent.handle_message(remote_jid=remote, text="chama o garcom")
        assert result["action"] == "service_requested"

    def test_derramei_retorna_service_requested(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000053"
        _activate_table(agent, remote, "Mesa 2")
        result = agent.handle_message(remote_jid=remote, text="derramei o copo")
        assert result["action"] == "service_requested"

    def test_service_requested_reply_contem_mesa(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000054"
        _activate_table(agent, remote, "Mesa 11")
        result = agent.handle_message(remote_jid=remote, text="preciso de talheres")
        assert "11" in result["reply"]


# ---------------------------------------------------------------------------
# handle_message — repeat sem pedido anterior
# ---------------------------------------------------------------------------

class HandleMessageRepeatSemPedidoTest(unittest.TestCase):
    def test_repete_sem_pedido_anterior_retorna_repeat_not_found(self):
        agent, *_ = make_environment()
        remote = "5511000000060"
        _activate_table(agent, remote, "Mesa 4")
        result = agent.handle_message(remote_jid=remote, text="repete")
        assert result["action"] == "repeat_not_found"

    def test_outra_rodada_sem_pedido_anterior_retorna_repeat_not_found(self):
        agent, *_ = make_environment()
        remote = "5511000000061"
        _activate_table(agent, remote, "Mesa 4")
        result = agent.handle_message(remote_jid=remote, text="outra rodada")
        assert result["action"] == "repeat_not_found"


# ---------------------------------------------------------------------------
# handle_message — repeat com pedido anterior
# ---------------------------------------------------------------------------

class HandleMessageRepeatComPedidoTest(unittest.TestCase):
    def _setup_with_delivered_order(self, remote: str, mesa: str, db: Database) -> RestaurantAgent:
        agent, orders, sessions, billing, _db = make_environment()
        _activate_table(agent, remote, mesa)

        agent.handle_message(remote_jid=remote, text="quero uma corona")
        pending = orders.pending_order(
            sessions.active_session_for_whatsapp(remote)["id"]
        )
        orders.confirm_order(pending["id"])
        db.execute("update pedidos set status = 'entregue' where id = ?", (pending["id"],))
        return agent

    def test_repete_com_pedido_anterior_retorna_order_draft_created(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000070"
        _activate_table(agent, remote, "Mesa 1")

        agent.handle_message(remote_jid=remote, text="quero uma corona")
        session = sessions.active_session_for_whatsapp(remote)
        pending = orders.pending_order(session["id"])
        orders.confirm_order(pending["id"])
        db.execute("update pedidos set status = 'entregue' where id = ?", (pending["id"],))

        result = agent.handle_message(remote_jid=remote, text="repete")
        assert result["action"] == "order_draft_created"

    def test_repete_reply_contem_confirma(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000071"
        _activate_table(agent, remote, "Mesa 1")

        agent.handle_message(remote_jid=remote, text="quero uma corona")
        session = sessions.active_session_for_whatsapp(remote)
        pending = orders.pending_order(session["id"])
        orders.confirm_order(pending["id"])
        db.execute("update pedidos set status = 'entregue' where id = ?", (pending["id"],))

        result = agent.handle_message(remote_jid=remote, text="repete")
        assert "Confirma" in result["reply"]


# ---------------------------------------------------------------------------
# handle_message — unavailable
# ---------------------------------------------------------------------------

class HandleMessageUnavailableTest(unittest.TestCase):
    def test_item_indisponivel_retorna_unavailable(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000080"
        _activate_table(agent, remote, "Mesa 3")
        db.execute("update produtos set disponivel = 0 where nome = 'Corona long neck'")
        result = agent.handle_message(remote_jid=remote, text="quero uma corona")
        assert result["action"] == "unavailable"

    def test_reply_unavailable_menciona_item(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000081"
        _activate_table(agent, remote, "Mesa 3")
        db.execute("update produtos set disponivel = 0 where nome = 'Corona long neck'")
        result = agent.handle_message(remote_jid=remote, text="quero uma corona")
        assert "Corona" in result["reply"]


# ---------------------------------------------------------------------------
# handle_message — human_called (nenhuma correspondência no cardápio)
# ---------------------------------------------------------------------------

class HandleMessageHumanCalledTest(unittest.TestCase):
    def test_item_inexistente_chama_atendente(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000090"
        _activate_table(agent, remote, "Mesa 8")
        result = agent.handle_message(
            remote_jid=remote, text="quero um prato que nao existe xyz abc"
        )
        assert result["action"] == "human_called"

    def test_human_called_cria_solicitacao_no_salao(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000091"
        _activate_table(agent, remote, "Mesa 8")
        agent.handle_message(
            remote_jid=remote, text="quero algo inexistente zzzyyy"
        )
        dash = orders.dashboard()
        assert len(dash["columns"]["salao"]) >= 1


# ---------------------------------------------------------------------------
# handle_message — account_requested via fechar conta
# ---------------------------------------------------------------------------

class HandleMessageAccountRequestedTest(unittest.TestCase):
    def test_pagar_retorna_account_requested(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000100"
        _activate_table(agent, remote, "Mesa 10")
        result = agent.handle_message(remote_jid=remote, text="pagar")
        assert result["action"] == "account_requested"

    def test_pay_retorna_account_requested_english(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000101"
        agent.handle_message(remote_jid=remote, text="Table 10")
        result = agent.handle_message(remote_jid=remote, text="pay")
        assert result["action"] == "account_requested"

    def test_account_requested_cria_solicitacao_no_caixa(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000102"
        _activate_table(agent, remote, "Mesa 10")
        agent.handle_message(remote_jid=remote, text="pagar")
        dash = orders.dashboard()
        assert len(dash["columns"]["caixa"]) >= 1

    def test_reply_account_requested_menciona_mesa(self):
        agent, orders, *_ = make_environment()
        remote = "5511000000103"
        _activate_table(agent, remote, "Mesa 10")
        result = agent.handle_message(remote_jid=remote, text="fecha a conta")
        assert "10" in result["reply"]


# ---------------------------------------------------------------------------
# handle_message — linguagem detectada a partir de "1"/"2" usa idioma do pedido
# ---------------------------------------------------------------------------

class HandleMessageLanguageFromPendingTest(unittest.TestCase):
    def test_confirmar_com_1_usa_idioma_do_pedido_pendente(self):
        # O pedido foi feito em inglês; ao confirmar com "1" deve usar inglês
        agent, orders, sessions, *_ = make_environment()
        remote = "447700900099"
        agent.handle_message(remote_jid=remote, text="Table 1")
        agent.handle_message(remote_jid=remote, text="Can I get two Coronas")
        result = agent.handle_message(remote_jid=remote, text="1")
        assert result["action"] == "order_confirmed"
        assert result["language"] == "en"

    def test_alterar_com_2_usa_idioma_do_pedido_pendente(self):
        agent, orders, sessions, *_ = make_environment()
        remote = "447700900098"
        agent.handle_message(remote_jid=remote, text="Table 2")
        agent.handle_message(remote_jid=remote, text="Can I get two Coronas")
        result = agent.handle_message(remote_jid=remote, text="2")
        assert result["action"] == "alter_order"
        assert result["language"] == "en"


# ---------------------------------------------------------------------------
# _handle_openai_result — testado via mock do interpreter
# ---------------------------------------------------------------------------

class HandleOpenAIResultTest(unittest.TestCase):
    """Usa mock do OpenAIInterpreter para controlar o retorno sem rede."""

    def _make_agent_with_mock_interpreter(
        self, openai_response: dict[str, Any] | None
    ) -> tuple[RestaurantAgent, OrderService, TableSessionService, Database]:
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        db = Database(handle.name)
        db.init_schema()
        db.seed_demo()
        billing = BillingService(db)
        sessions = TableSessionService(db, billing=billing)
        menu = MenuService(db)
        orders = OrderService(db)

        mock_interpreter = MagicMock(spec=OpenAIInterpreter)
        mock_interpreter.interpret.return_value = openai_response

        agent = RestaurantAgent(
            table_sessions=sessions,
            menu=menu,
            orders=orders,
            interpreter=mock_interpreter,
            billing=billing,
        )
        return agent, orders, sessions, db

    def test_clarification_question_retorna_clarification_needed(self):
        response = {
            "intent": "unknown",
            "items": [],
            "service_description": "",
            "clarification_question": "Você quer Brahma lata ou garrafa?",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000200"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero uma brahma ai")
        assert result["action"] == "clarification_needed"
        assert "Brahma" in result["reply"]

    def test_intent_close_account_via_openai_retorna_account_requested(self):
        response = {
            "intent": "close_account",
            "items": [],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000201"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero fechar minha conta agora")
        assert result["action"] == "account_requested"

    def test_intent_service_via_openai_retorna_service_requested(self):
        response = {
            "intent": "service",
            "items": [],
            "service_description": "Precisa de ajuda na mesa",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000202"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="socorro preciso de ajuda")
        assert result["action"] == "service_requested"

    def test_intent_order_com_produto_valido_retorna_draft(self):
        # Precisa do nome exato que product_by_name_or_alias encontra
        response = {
            "intent": "order",
            "items": [{"name": "corona", "quantity": 2, "notes": ""}],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000203"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero duas coronas")
        assert result["action"] == "order_draft_created"

    def test_intent_order_quantidade_minima_1(self):
        # quantity=0 deve ser tratado como 1 (max(1, int(0)))
        response = {
            "intent": "order",
            "items": [{"name": "corona", "quantity": 0, "notes": ""}],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000204"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero corona")
        assert result["action"] == "order_draft_created"
        item = result["order"]["items"][0]
        assert item["quantidade"] >= 1

    def test_intent_order_produto_inexistente_avisa_unavailable(self):
        # Um unico item inexistente nao deve sumir silenciosamente: o agente
        # responde 'unavailable' citando o nome pedido, em vez de descartar tudo.
        response = {
            "intent": "order",
            "items": [{"name": "produto que nao existe xyzxyz", "quantity": 1, "notes": ""}],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000205"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(
            remote_jid=remote, text="quero algo inexistente xyzxyz total"
        )
        assert result["action"] == "unavailable"
        assert "produto que nao existe xyzxyz" in result["reply"]

    def test_intent_order_produto_indisponivel_retorna_none_e_cai_no_heuristico(self):
        # Quando o produto existe mas nao está disponível, _handle_openai_result retorna None
        response = {
            "intent": "order",
            "items": [{"name": "corona", "quantity": 1, "notes": ""}],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, billing, db = make_environment()
        db.execute("update produtos set disponivel = 0 where nome = 'Corona long neck'")

        mock_interpreter = MagicMock(spec=OpenAIInterpreter)
        mock_interpreter.interpret.return_value = response

        sessions2 = TableSessionService(db, billing=billing)
        menu2 = MenuService(db)
        orders2 = OrderService(db)
        agent2 = RestaurantAgent(
            table_sessions=sessions2,
            menu=menu2,
            orders=orders2,
            interpreter=mock_interpreter,
            billing=billing,
        )
        remote = "5511000000206"
        agent2.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent2.handle_message(remote_jid=remote, text="quero uma corona")
        # _handle_openai_result retorna None => find_items encontra indisponivel => unavailable
        assert result["action"] == "unavailable"

    def test_intent_order_parcial_cria_pedido_e_avisa_faltante(self):
        # Pedido com um item valido (corona) e um inexistente: o agente cria o
        # draft so com o valido e adiciona um aviso sobre o que faltou.
        response = {
            "intent": "order",
            "items": [
                {"name": "corona", "quantity": 1, "notes": ""},
                {"name": "produto fantasma xyzxyz", "quantity": 1, "notes": ""},
            ],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000299"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero uma corona e um fantasma")

        # Pedido foi criado apenas com o item valido
        assert result["action"] == "order_draft_created"
        nomes = [
            (item.get("nome") or item.get("nome_snapshot") or "")
            for item in result["order"]["items"]
        ]
        assert any("Corona" in nome for nome in nomes)
        assert all("fantasma" not in nome.lower() for nome in nomes)
        # E o cliente foi avisado do item que faltou
        assert "produto fantasma xyzxyz" in result["reply"]

    def test_intent_order_lista_vazia_retorna_none(self):
        # items=[] => _handle_openai_result retorna None => cai no heurístico
        response = {
            "intent": "order",
            "items": [],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000207"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="quero nada especifico")
        # Com items=[], _handle_openai_result retorna None; heurístico também não acha nada => human_called
        assert result["action"] == "human_called"

    def test_intent_unknown_retorna_none_e_cai_no_heuristico(self):
        response = {
            "intent": "unknown",
            "items": [],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000208"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="nao sei o que quero agora xyz")
        # intent=unknown sem clarification_question => retorna None => heurístico => human_called
        assert result["action"] == "human_called"

    def test_intent_repeat_via_openai_sem_pedido_anterior_retorna_none_e_continua(self):
        # intent=repeat sem draft disponível => _handle_openai_result retorna None
        # O fluxo continua para find_items heuristico, que nao encontra nada => human_called
        response = {
            "intent": "repeat",
            "items": [],
            "service_description": "",
            "clarification_question": "",
        }
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(response)
        remote = "5511000000209"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        result = agent.handle_message(remote_jid=remote, text="me repete aquilo la ok")
        # sem pedido entregue, create_repeat_draft retorna None =>
        # _handle_openai_result retorna None => heuristico => human_called
        assert result["action"] in ("human_called", "repeat_not_found")

    def test_interpreter_none_retorno_cai_no_heuristico(self):
        # interpreter.interpret retorna None (sem chave OpenAI)
        agent, orders, sessions, db = self._make_agent_with_mock_interpreter(None)
        remote = "5511000000210"
        agent.handle_message(remote_jid=remote, text="Mesa 5")
        # mensagem que o heurístico encontra (corona)
        result = agent.handle_message(remote_jid=remote, text="quero uma corona")
        assert result["action"] == "order_draft_created"


# ---------------------------------------------------------------------------
# handle_message — origem passada corretamente
# ---------------------------------------------------------------------------

class HandleMessageOrigemTest(unittest.TestCase):
    def test_origem_audio_persistida(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000300"
        _activate_table(agent, remote, "Mesa 2")
        agent.handle_message(remote_jid=remote, text="quero uma corona", origem="audio")
        session = sessions.active_session_for_whatsapp(remote)
        pending = orders.pending_order(session["id"])
        assert pending is not None
        row = db.fetchone(
            "select origem from pedidos where id = ?", (pending["id"],)
        )
        assert row["origem"] == "audio"

    def test_origem_padrao_e_whatsapp(self):
        agent, orders, sessions, billing, db = make_environment()
        remote = "5511000000301"
        _activate_table(agent, remote, "Mesa 2")
        agent.handle_message(remote_jid=remote, text="quero uma corona")
        session = sessions.active_session_for_whatsapp(remote)
        pending = orders.pending_order(session["id"])
        row = db.fetchone(
            "select origem from pedidos where id = ?", (pending["id"],)
        )
        assert row["origem"] == "whatsapp"


if __name__ == "__main__":
    unittest.main()
