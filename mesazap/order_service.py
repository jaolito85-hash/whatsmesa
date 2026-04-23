from __future__ import annotations

from collections import defaultdict
from typing import Any

from .storage import Database, new_id, utc_now


ITEM_STATUS_NEXT = {
    "novo": "em_preparo",
    "em_preparo": "pronto",
    "pronto": "entregue",
}

REQUEST_STATUS_NEXT = {
    "nova": "em_atendimento",
    "em_atendimento": "concluida",
}


class OrderService:
    def __init__(self, db: Database):
        self.db = db

    def pending_order(self, session_id: str) -> dict[str, Any] | None:
        order = self.db.fetchone(
            """
            select *
            from pedidos
            where sessao_mesa_id = ? and status = 'aguardando_confirmacao_cliente'
            order by criado_em desc
            limit 1
            """,
            (session_id,),
        )
        if order:
            order["items"] = self.items_for_order(order["id"])
        return order

    def items_for_order(self, order_id: str) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "select * from pedido_itens where pedido_id = ? order by setor, nome_snapshot",
            (order_id,),
        )

    def create_draft_order(
        self,
        *,
        session: dict[str, Any],
        items: list[dict[str, Any]],
        texto_original: str,
        origem: str,
    ) -> dict[str, Any]:
        total = sum(item["quantidade"] * float(item["preco"]) for item in items)
        order_id = new_id()
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                insert into pedidos (
                  id, restaurante_id, unidade_id, mesa_id, sessao_mesa_id,
                  cliente_whatsapp, status, total_estimado, texto_original,
                  origem, criado_em
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    session["restaurante_id"],
                    session["unidade_id"],
                    session["mesa_id"],
                    session["id"],
                    session["cliente_whatsapp"],
                    "aguardando_confirmacao_cliente",
                    total,
                    texto_original,
                    origem,
                    now,
                ),
            )
            for item in items:
                conn.execute(
                    """
                    insert into pedido_itens (
                      id, pedido_id, produto_id, nome_snapshot, quantidade,
                      preco_unitario_snapshot, setor, observacoes, status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, 'novo')
                    """,
                    (
                        new_id(),
                        order_id,
                        item["product_id"],
                        item["nome"],
                        item["quantidade"],
                        item["preco"],
                        item["setor"],
                        item.get("observacoes", ""),
                    ),
                )

        created = self.db.fetchone("select * from pedidos where id = ?", (order_id,))
        if not created:
            raise RuntimeError("Pedido nao encontrado depois de criar rascunho.")
        created["items"] = self.items_for_order(order_id)
        return created

    def confirm_order(self, order_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                update pedidos
                set status = 'enviado_setor', confirmado_em = ?
                where id = ? and status = 'aguardando_confirmacao_cliente'
                """,
                (now, order_id),
            )
            conn.execute(
                """
                insert into eventos_pedido (id, pedido_id, tipo, descricao, criado_por, criado_em)
                values (?, ?, 'pedido_confirmado', 'Cliente confirmou o pedido no WhatsApp.', 'cliente', ?)
                """,
                (new_id(), order_id, now),
            )

        order = self.db.fetchone("select * from pedidos where id = ?", (order_id,))
        if not order:
            raise RuntimeError("Pedido nao encontrado.")
        order["items"] = self.items_for_order(order_id)
        order["setores"] = sorted({item["setor"] for item in order["items"]})
        return order

    def create_service_request(
        self,
        *,
        session: dict[str, Any],
        tipo: str,
        descricao: str,
        setor: str = "salao",
    ) -> dict[str, Any]:
        request_id = new_id()
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                insert into solicitacoes_salao (
                  id, restaurante_id, mesa_id, sessao_mesa_id, tipo,
                  descricao, setor, status, criada_em
                ) values (?, ?, ?, ?, ?, ?, ?, 'nova', ?)
                """,
                (
                    request_id,
                    session["restaurante_id"],
                    session["mesa_id"],
                    session["id"],
                    tipo,
                    descricao,
                    setor,
                    now,
                ),
            )

        created = self.db.fetchone("select * from solicitacoes_salao where id = ?", (request_id,))
        if not created:
            raise RuntimeError("Solicitacao nao encontrada depois de criar.")
        return created

    def create_repeat_draft(self, session: dict[str, Any]) -> dict[str, Any] | None:
        rows = self.db.fetchall(
            """
            select i.produto_id as product_id, i.nome_snapshot as nome,
                   i.quantidade, i.preco_unitario_snapshot as preco,
                   i.setor, i.observacoes
            from pedidos p
            join pedido_itens i on i.pedido_id = p.id
            where p.sessao_mesa_id = ?
              and p.status in ('enviado_setor', 'em_preparo', 'pronto', 'entregue')
              and i.setor = 'bar'
              and i.status != 'cancelado'
            order by p.confirmado_em desc
            limit 8
            """,
            (session["id"],),
        )
        if not rows:
            return None
        return self.create_draft_order(
            session=session,
            items=rows,
            texto_original="Repetir rodada anterior",
            origem="whatsapp",
        )

    def dashboard(self) -> dict[str, Any]:
        item_rows = self.db.fetchall(
            """
            select i.*, p.mesa_id, p.sessao_mesa_id, p.status as pedido_status,
                   p.criado_em, p.confirmado_em, m.numero as mesa_numero
            from pedido_itens i
            join pedidos p on p.id = i.pedido_id
            join mesas m on m.id = p.mesa_id
            where p.status in ('enviado_setor', 'em_preparo', 'pronto', 'entregue')
              and i.status != 'cancelado'
            order by p.confirmado_em desc, i.setor, m.numero
            """
        )
        request_rows = self.db.fetchall(
            """
            select r.*, m.numero as mesa_numero
            from solicitacoes_salao r
            join mesas m on m.id = r.mesa_id
            where r.status != 'cancelada'
            order by r.criada_em desc
            """
        )

        columns: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in item_rows:
            columns[row["setor"]].append(
                {
                    "kind": "item",
                    "id": row["id"],
                    "mesa": row["mesa_numero"],
                    "titulo": row["nome_snapshot"],
                    "quantidade": row["quantidade"],
                    "observacoes": row["observacoes"] or "",
                    "status": row["status"],
                    "horario": row["confirmado_em"] or row["criado_em"],
                    "next_status": ITEM_STATUS_NEXT.get(row["status"]),
                }
            )

        for row in request_rows:
            sector = row["setor"] if row["setor"] in {"salao", "caixa"} else "salao"
            columns[sector].append(
                {
                    "kind": "request",
                    "id": row["id"],
                    "mesa": row["mesa_numero"],
                    "titulo": row["descricao"],
                    "quantidade": 1,
                    "observacoes": row["tipo"].replace("_", " "),
                    "status": row["status"],
                    "horario": row["criada_em"],
                    "next_status": REQUEST_STATUS_NEXT.get(row["status"]),
                }
            )

        tables = self.db.fetchall(
            """
            select status, count(*) as total
            from mesas
            group by status
            order by status
            """
        )
        pending = self.db.fetchall(
            """
            select p.*, m.numero as mesa_numero
            from pedidos p
            join mesas m on m.id = p.mesa_id
            where p.status = 'aguardando_confirmacao_cliente'
            order by p.criado_em desc
            limit 8
            """
        )
        for order in pending:
            order["items"] = self.items_for_order(order["id"])

        return {
            "columns": {sector: columns.get(sector, []) for sector in ["bar", "cozinha", "salao", "caixa"]},
            "table_status": tables,
            "pending_orders": pending,
        }

    def update_item_status(self, item_id: str, status: str) -> None:
        allowed = {"novo", "em_preparo", "pronto", "entregue", "cancelado"}
        if status not in allowed:
            raise ValueError("Status de item invalido.")
        self.db.execute("update pedido_itens set status = ? where id = ?", (status, item_id))

    def update_request_status(self, request_id: str, status: str) -> None:
        allowed = {"nova", "em_atendimento", "concluida", "cancelada"}
        if status not in allowed:
            raise ValueError("Status de solicitacao invalido.")
        completed_at = utc_now() if status == "concluida" else None
        self.db.execute(
            """
            update solicitacoes_salao
            set status = ?, concluida_em = coalesce(?, concluida_em)
            where id = ?
            """,
            (status, completed_at, request_id),
        )

