from __future__ import annotations

import tempfile
import unittest

from klink.order_service import ITEM_STATUS_NEXT, REQUEST_STATUS_NEXT, OrderService
from klink.storage import Database
from klink.table_session_service import TableSessionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_environment() -> tuple[OrderService, TableSessionService, Database]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    orders = OrderService(db)
    sessions = TableSessionService(db)
    return orders, sessions, db


def _sample_session(sessions: TableSessionService, remote: str = "5511900000099", mesa: str = "Mesa 5") -> dict:
    return sessions.activate_from_message(remote, mesa)


def _sample_items(db: Database, quantidade_1: int = 1, quantidade_2: int = 1) -> list[dict]:
    """Retorna dois itens do cardapio demo (bar + cozinha)."""
    corona = db.fetchone("select * from produtos where nome = 'Corona long neck'")
    batata = db.fetchone("select * from produtos where nome = 'Porcao de batata frita'")
    return [
        {
            "product_id": corona["id"],
            "nome": corona["nome"],
            "quantidade": quantidade_1,
            "preco": corona["preco"],
            "setor": corona["setor"],
            "observacoes": "",
        },
        {
            "product_id": batata["id"],
            "nome": batata["nome"],
            "quantidade": quantidade_2,
            "preco": batata["preco"],
            "setor": batata["setor"],
            "observacoes": "",
        },
    ]


# ---------------------------------------------------------------------------
# Dicionarios de transicao de status
# ---------------------------------------------------------------------------

class ItemStatusNextTest(unittest.TestCase):
    def test_novo_avancar_para_em_preparo(self):
        assert ITEM_STATUS_NEXT["novo"] == "em_preparo"

    def test_em_preparo_avancar_para_pronto(self):
        assert ITEM_STATUS_NEXT["em_preparo"] == "pronto"

    def test_pronto_avancar_para_entregue(self):
        assert ITEM_STATUS_NEXT["pronto"] == "entregue"

    def test_entregue_nao_tem_proximo(self):
        assert "entregue" not in ITEM_STATUS_NEXT

    def test_cancelado_nao_tem_proximo(self):
        assert "cancelado" not in ITEM_STATUS_NEXT


class RequestStatusNextTest(unittest.TestCase):
    def test_nova_avancar_para_em_atendimento(self):
        assert REQUEST_STATUS_NEXT["nova"] == "em_atendimento"

    def test_em_atendimento_avancar_para_concluida(self):
        assert REQUEST_STATUS_NEXT["em_atendimento"] == "concluida"

    def test_concluida_nao_tem_proximo(self):
        assert "concluida" not in REQUEST_STATUS_NEXT

    def test_cancelada_nao_tem_proximo(self):
        assert "cancelada" not in REQUEST_STATUS_NEXT


# ---------------------------------------------------------------------------
# create_draft_order — criacao e calculo de total
# ---------------------------------------------------------------------------

class CreateDraftOrderTest(unittest.TestCase):
    def test_cria_pedido_com_status_aguardando_confirmacao(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session,
            items=items,
            texto_original="Me ve 1 corona e batata",
            origem="whatsapp",
        )

        assert pedido["status"] == "aguardando_confirmacao_cliente"
        assert pedido["sessao_mesa_id"] == session["id"]

    def test_calculo_total_um_item(self):
        # Corona = R$14,00 x 3 = R$42,00
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        corona = db.fetchone("select * from produtos where nome = 'Corona long neck'")
        items = [
            {
                "product_id": corona["id"],
                "nome": corona["nome"],
                "quantidade": 3,
                "preco": corona["preco"],
                "setor": corona["setor"],
                "observacoes": "",
            }
        ]

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="3 coronas", origem="whatsapp"
        )

        assert abs(pedido["total_estimado"] - 42.0) < 0.001

    def test_calculo_total_multiplos_itens_e_quantidades(self):
        # Corona R$14,00 x 2 = R$28,00
        # Batata R$32,00 x 1 = R$32,00
        # Total = R$60,00
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db, quantidade_1=2, quantidade_2=1)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="2 coronas e batata", origem="whatsapp"
        )

        assert abs(pedido["total_estimado"] - 60.0) < 0.001

    def test_total_zero_lista_vazia(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        pedido = orders.create_draft_order(
            session=session, items=[], texto_original="(vazio)", origem="whatsapp"
        )

        assert pedido["total_estimado"] == 0.0

    def test_itens_persistidos_com_status_novo(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="corona e batata", origem="whatsapp"
        )

        for item in pedido["items"]:
            assert item["status"] == "novo", f"Item {item['nome_snapshot']} com status inesperado: {item['status']}"

    def test_retorno_inclui_lista_de_itens(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )

        assert "items" in pedido
        assert len(pedido["items"]) == 2

    def test_origem_e_texto_original_persistidos(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session,
            items=items,
            texto_original="pedido original do cliente",
            origem="whatsapp",
        )

        row = db.fetchone("select texto_original, origem from pedidos where id = ?", (pedido["id"],))
        assert row["texto_original"] == "pedido original do cliente"
        assert row["origem"] == "whatsapp"


# ---------------------------------------------------------------------------
# pending_order
# ---------------------------------------------------------------------------

class PendingOrderTest(unittest.TestCase):
    def test_retorna_pedido_pendente_da_sessao(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )

        pendente = orders.pending_order(session["id"])
        assert pendente is not None
        assert pendente["id"] == pedido["id"]

    def test_retorna_none_quando_nao_ha_pedido_pendente(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        pendente = orders.pending_order(session["id"])
        assert pendente is None

    def test_pedido_confirmado_nao_aparece_como_pendente(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])

        pendente = orders.pending_order(session["id"])
        assert pendente is None

    def test_sessao_diferente_nao_ve_pedido_da_outra(self):
        orders, sessions, db = make_environment()
        session_a = _sample_session(sessions, remote="5511100000001", mesa="Mesa 1")
        session_b = _sample_session(sessions, remote="5511100000002", mesa="Mesa 2")
        items = _sample_items(db)

        orders.create_draft_order(
            session=session_a, items=items, texto_original="teste", origem="whatsapp"
        )

        pendente_b = orders.pending_order(session_b["id"])
        assert pendente_b is None

    def test_retorna_um_pedido_quando_ha_dois_pendentes(self):
        # Dois rascunhos na mesma sessao: pending_order retorna exatamente um deles.
        # utc_now() tem resolucao de segundos, entao os dois podem ter criado_em
        # identico — nao e possivel garantir qual dos dois volta sem controlar o
        # relogio. O que importa testar e que a funcao retorna um resultado valido
        # (nao None) e que ele pertence a sessao correta.
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        first = orders.create_draft_order(
            session=session, items=items, texto_original="primeiro", origem="whatsapp"
        )
        second = orders.create_draft_order(
            session=session, items=items, texto_original="segundo", origem="whatsapp"
        )

        pendente = orders.pending_order(session["id"])
        assert pendente is not None
        assert pendente["id"] in {first["id"], second["id"]}
        assert pendente["sessao_mesa_id"] == session["id"]


# ---------------------------------------------------------------------------
# confirm_order
# ---------------------------------------------------------------------------

class ConfirmOrderTest(unittest.TestCase):
    def test_muda_status_para_enviado_setor(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        confirmado = orders.confirm_order(pedido["id"])

        assert confirmado["status"] == "enviado_setor"

    def test_preenche_confirmado_em(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        confirmado = orders.confirm_order(pedido["id"])

        assert confirmado["confirmado_em"] is not None

    def test_retorno_inclui_setores(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)  # bar + cozinha

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="corona e batata", origem="whatsapp"
        )
        confirmado = orders.confirm_order(pedido["id"])

        assert "setores" in confirmado
        assert "bar" in confirmado["setores"]
        assert "cozinha" in confirmado["setores"]

    def test_insere_evento_pedido_confirmado(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])

        evento = db.fetchone(
            "select tipo from eventos_pedido where pedido_id = ?",
            (pedido["id"],),
        )
        assert evento is not None
        assert evento["tipo"] == "pedido_confirmado"

    def test_confirmar_ja_confirmado_e_idempotente(self):
        # confirm_order usa WHERE status = 'aguardando_confirmacao_cliente', entao
        # uma segunda chamada nao altera o status nem o confirmado_em do pedido.
        # O INSERT do evento e condicionado ao rowcount do UPDATE, portanto uma
        # segunda confirmacao NAO cria um segundo evento 'pedido_confirmado'.
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        primeira = orders.confirm_order(pedido["id"])
        segunda = orders.confirm_order(pedido["id"])

        # Status permanece enviado_setor nas duas respostas
        assert primeira["status"] == "enviado_setor"
        assert segunda["status"] == "enviado_setor"

        # confirmado_em nao retrocede / nao muda na segunda chamada
        assert primeira["confirmado_em"] == segunda["confirmado_em"]

        # Apenas um evento 'pedido_confirmado' foi registrado, mesmo apos duas chamadas
        eventos = db.fetchall(
            "select id from eventos_pedido where pedido_id = ? and tipo = 'pedido_confirmado'",
            (pedido["id"],),
        )
        assert len(eventos) == 1

        # confirmado_em nao e apagado pela segunda chamada
        row = db.fetchone("select status, confirmado_em from pedidos where id = ?", (pedido["id"],))
        assert row["status"] == "enviado_setor"
        assert row["confirmado_em"] is not None


# ---------------------------------------------------------------------------
# update_item_status
# ---------------------------------------------------------------------------

class UpdateItemStatusTest(unittest.TestCase):
    def _criar_item_id(self, orders: OrderService, sessions: TableSessionService, db: Database) -> str:
        session = _sample_session(sessions, remote="5511200000001", mesa="Mesa 3")
        items = _sample_items(db)
        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        return pedido["items"][0]["id"]

    def test_transicao_novo_para_em_preparo(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        orders.update_item_status(item_id, "em_preparo")
        row = db.fetchone("select status from pedido_itens where id = ?", (item_id,))
        assert row["status"] == "em_preparo"

    def test_transicao_em_preparo_para_pronto(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        orders.update_item_status(item_id, "em_preparo")
        orders.update_item_status(item_id, "pronto")
        row = db.fetchone("select status from pedido_itens where id = ?", (item_id,))
        assert row["status"] == "pronto"

    def test_transicao_pronto_para_entregue(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        orders.update_item_status(item_id, "em_preparo")
        orders.update_item_status(item_id, "pronto")
        orders.update_item_status(item_id, "entregue")
        row = db.fetchone("select status from pedido_itens where id = ?", (item_id,))
        assert row["status"] == "entregue"

    def test_cancelar_item(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        orders.update_item_status(item_id, "cancelado")
        row = db.fetchone("select status from pedido_itens where id = ?", (item_id,))
        assert row["status"] == "cancelado"

    def test_status_invalido_lanca_value_error(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        try:
            orders.update_item_status(item_id, "inexistente")
            assert False, "Deveria ter lancado ValueError"
        except ValueError:
            pass

    def test_status_vazio_lanca_value_error(self):
        orders, sessions, db = make_environment()
        item_id = self._criar_item_id(orders, sessions, db)
        try:
            orders.update_item_status(item_id, "")
            assert False, "Deveria ter lancado ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# create_service_request
# ---------------------------------------------------------------------------

class CreateServiceRequestTest(unittest.TestCase):
    def test_cria_solicitacao_com_status_nova(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        req = orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Pode fechar a conta",
        )

        assert req["status"] == "nova"

    def test_setor_padrao_e_salao(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        req = orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao="Preciso de ajuda",
        )

        assert req["setor"] == "salao"

    def test_setor_caixa_persiste(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        req = orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Fecha conta",
            setor="caixa",
        )

        assert req["setor"] == "caixa"

    def test_vinculado_a_sessao_correta(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        req = orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Fechar",
            setor="caixa",
        )

        assert req["sessao_mesa_id"] == session["id"]
        assert req["mesa_id"] == session["mesa_id"]
        assert req["restaurante_id"] == session["restaurante_id"]

    def test_get_request_retorna_solicitacao(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        req = orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao="Por favor",
        )

        loaded = orders.get_request(req["id"])
        assert loaded is not None
        assert loaded["id"] == req["id"]
        assert loaded["tipo"] == "chamar_garcom"

    def test_get_request_inexistente_retorna_none(self):
        orders, sessions, db = make_environment()
        result = orders.get_request("id-que-nao-existe")
        assert result is None


# ---------------------------------------------------------------------------
# update_request_status
# ---------------------------------------------------------------------------

class UpdateRequestStatusTest(unittest.TestCase):
    def _criar_solicitacao(self, orders: OrderService, sessions: TableSessionService, remote: str = "5511300000001") -> dict:
        session = _sample_session(sessions, remote=remote, mesa="Mesa 4")
        return orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao="Preciso de ajuda",
        )

    def test_transicao_nova_para_em_atendimento(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        orders.update_request_status(req["id"], "em_atendimento")
        row = db.fetchone("select status from solicitacoes_salao where id = ?", (req["id"],))
        assert row["status"] == "em_atendimento"

    def test_transicao_em_atendimento_para_concluida(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        orders.update_request_status(req["id"], "em_atendimento")
        orders.update_request_status(req["id"], "concluida")
        row = db.fetchone("select status from solicitacoes_salao where id = ?", (req["id"],))
        assert row["status"] == "concluida"

    def test_concluida_preenche_concluida_em(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        orders.update_request_status(req["id"], "concluida")
        row = db.fetchone("select concluida_em from solicitacoes_salao where id = ?", (req["id"],))
        assert row["concluida_em"] is not None

    def test_cancelada_nao_preenche_concluida_em(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        orders.update_request_status(req["id"], "cancelada")
        row = db.fetchone("select status, concluida_em from solicitacoes_salao where id = ?", (req["id"],))
        assert row["status"] == "cancelada"
        assert row["concluida_em"] is None

    def test_status_invalido_lanca_value_error(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        try:
            orders.update_request_status(req["id"], "status_inexistente")
            assert False, "Deveria ter lancado ValueError"
        except ValueError:
            pass

    def test_status_vazio_lanca_value_error(self):
        orders, sessions, db = make_environment()
        req = self._criar_solicitacao(orders, sessions)
        try:
            orders.update_request_status(req["id"], "")
            assert False, "Deveria ter lancado ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# create_repeat_draft
# ---------------------------------------------------------------------------

class CreateRepeatDraftTest(unittest.TestCase):
    def test_retorna_none_sem_pedidos_anteriores(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        result = orders.create_repeat_draft(session)
        assert result is None

    def test_retorna_none_somente_com_pedidos_de_cozinha(self):
        # Pedidos apenas de cozinha nao devem gerar repeat (so bar e elegivel)
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        batata = db.fetchone("select * from produtos where nome = 'Porcao de batata frita'")
        items_cozinha = [
            {
                "product_id": batata["id"],
                "nome": batata["nome"],
                "quantidade": 1,
                "preco": batata["preco"],
                "setor": batata["setor"],
                "observacoes": "",
            }
        ]
        pedido = orders.create_draft_order(
            session=session, items=items_cozinha, texto_original="batata", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])
        # Avanca status para 'entregue' para ser elegivel
        db.execute("update pedidos set status = 'entregue' where id = ?", (pedido["id"],))

        result = orders.create_repeat_draft(session)
        assert result is None

    def test_cria_rascunho_com_itens_do_bar(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        corona = db.fetchone("select * from produtos where nome = 'Corona long neck'")
        items_bar = [
            {
                "product_id": corona["id"],
                "nome": corona["nome"],
                "quantidade": 2,
                "preco": corona["preco"],
                "setor": corona["setor"],
                "observacoes": "",
            }
        ]
        pedido = orders.create_draft_order(
            session=session, items=items_bar, texto_original="corona", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])
        db.execute("update pedidos set status = 'entregue' where id = ?", (pedido["id"],))

        repeat = orders.create_repeat_draft(session)
        assert repeat is not None
        assert repeat["status"] == "aguardando_confirmacao_cliente"
        nomes = [i["nome_snapshot"] for i in repeat["items"]]
        assert "Corona long neck" in nomes

    def test_texto_original_repeat_e_descritivo(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        corona = db.fetchone("select * from produtos where nome = 'Corona long neck'")
        items_bar = [
            {
                "product_id": corona["id"],
                "nome": corona["nome"],
                "quantidade": 1,
                "preco": corona["preco"],
                "setor": corona["setor"],
                "observacoes": "",
            }
        ]
        pedido = orders.create_draft_order(
            session=session, items=items_bar, texto_original="corona", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])
        db.execute("update pedidos set status = 'entregue' where id = ?", (pedido["id"],))

        repeat = orders.create_repeat_draft(session)
        assert repeat["texto_original"] == "Repetir rodada anterior"


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

class DashboardTest(unittest.TestCase):
    def test_dashboard_retorna_quatro_colunas(self):
        orders, sessions, db = make_environment()
        dash = orders.dashboard()
        assert set(dash["columns"].keys()) == {"bar", "cozinha", "salao", "caixa"}

    def test_dashboard_sem_pedidos_colunas_vazias(self):
        orders, sessions, db = make_environment()
        dash = orders.dashboard()
        for col in ["bar", "cozinha", "salao", "caixa"]:
            assert dash["columns"][col] == []

    def test_pedido_confirmado_aparece_no_dashboard(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="corona e batata", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])

        dash = orders.dashboard()
        # Corona vai para bar, batata vai para cozinha
        assert len(dash["columns"]["bar"]) >= 1
        assert len(dash["columns"]["cozinha"]) >= 1

    def test_pedido_pendente_nao_aparece_nas_colunas(self):
        # Pedidos em aguardando_confirmacao_cliente devem aparecer em pending_orders,
        # nao nas colunas de producao
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )

        dash = orders.dashboard()
        for col in ["bar", "cozinha"]:
            assert len(dash["columns"][col]) == 0

    def test_pending_orders_contem_pedido_em_aguardando(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="corona e batata", origem="whatsapp"
        )

        dash = orders.dashboard()
        ids_pendentes = [p["id"] for p in dash["pending_orders"]]
        assert pedido["id"] in ids_pendentes

    def test_itens_cancelados_nao_aparecem_no_dashboard(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])

        for item in pedido["items"]:
            orders.update_item_status(item["id"], "cancelado")

        dash = orders.dashboard()
        for col in ["bar", "cozinha"]:
            assert len(dash["columns"][col]) == 0

    def test_solicatacao_salao_aparece_na_coluna_salao(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao="Preciso de ajuda",
            setor="salao",
        )

        dash = orders.dashboard()
        assert len(dash["columns"]["salao"]) == 1
        assert dash["columns"]["salao"][0]["kind"] == "request"

    def test_solicatacao_caixa_aparece_na_coluna_caixa(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Fechar conta",
            setor="caixa",
        )

        dash = orders.dashboard()
        assert len(dash["columns"]["caixa"]) == 1

    def test_next_status_item_no_dashboard(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        corona = db.fetchone("select * from produtos where nome = 'Corona long neck'")
        items_bar = [
            {
                "product_id": corona["id"],
                "nome": corona["nome"],
                "quantidade": 1,
                "preco": corona["preco"],
                "setor": corona["setor"],
                "observacoes": "",
            }
        ]
        pedido = orders.create_draft_order(
            session=session, items=items_bar, texto_original="corona", origem="whatsapp"
        )
        orders.confirm_order(pedido["id"])

        dash = orders.dashboard()
        item_no_dash = dash["columns"]["bar"][0]
        assert item_no_dash["next_status"] == "em_preparo"

    def test_next_status_request_no_dashboard(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao="Ajuda",
            setor="salao",
        )

        dash = orders.dashboard()
        req_no_dash = dash["columns"]["salao"][0]
        assert req_no_dash["next_status"] == "em_atendimento"


# ---------------------------------------------------------------------------
# items_for_order
# ---------------------------------------------------------------------------

class ItemsForOrderTest(unittest.TestCase):
    def test_retorna_lista_ordenada_por_setor_e_nome(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)
        items = _sample_items(db)

        pedido = orders.create_draft_order(
            session=session, items=items, texto_original="teste", origem="whatsapp"
        )

        recovered = orders.items_for_order(pedido["id"])
        setores = [i["setor"] for i in recovered]
        # Deve estar ordenado (bar vem antes de cozinha)
        assert setores == sorted(setores)

    def test_retorna_lista_vazia_para_pedido_sem_itens(self):
        orders, sessions, db = make_environment()
        session = _sample_session(sessions)

        pedido = orders.create_draft_order(
            session=session, items=[], texto_original="vazio", origem="whatsapp"
        )

        itens = orders.items_for_order(pedido["id"])
        assert itens == []


if __name__ == "__main__":
    unittest.main()
