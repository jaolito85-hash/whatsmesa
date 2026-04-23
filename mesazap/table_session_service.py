from __future__ import annotations

import re
from typing import Any

from .storage import Database, new_id, utc_now
from .text_utils import normalize_text


ACTIVE_SESSION_STATUSES = ("sessao_pendente", "sessao_ativa", "conta_solicitada")


class TableSessionService:
    def __init__(self, db: Database):
        self.db = db

    def parse_table_number(self, text: str) -> int | None:
        normalized = normalize_text(text)
        match = re.search(r"\b(?:mesa|table)\s*(\d{1,3})\b", normalized)
        if match:
            return int(match.group(1))
        compact = normalized.replace(" ", "")
        match = re.search(r"(?:mesa|table)(\d{1,3})", compact)
        return int(match.group(1)) if match else None

    def restaurant(self) -> dict[str, Any]:
        row = self.db.fetchone("select * from restaurantes where ativo = 1 order by criado_em limit 1")
        if not row:
            raise RuntimeError("Nenhum restaurante ativo cadastrado.")
        return row

    def table_by_number(self, number: int) -> dict[str, Any] | None:
        restaurant = self.restaurant()
        return self.db.fetchone(
            """
            select *
            from mesas
            where restaurante_id = ? and numero = ? and ativa = 1
            limit 1
            """,
            (restaurant["id"], number),
        )

    def table_by_token(self, token: str) -> dict[str, Any] | None:
        return self.db.fetchone(
            "select * from mesas where qr_token_atual = ? and ativa = 1",
            (token,),
        )

    def active_session_for_whatsapp(self, remote_jid: str) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        return self.db.fetchone(
            f"""
            select s.*, m.numero as mesa_numero, m.nome as mesa_nome
            from sessoes_mesa s
            join mesas m on m.id = s.mesa_id
            where s.cliente_whatsapp = ?
              and s.status in ({placeholders})
            order by s.aberta_em desc
            limit 1
            """,
            (remote_jid, *ACTIVE_SESSION_STATUSES),
        )

    def activate_from_message(self, remote_jid: str, text: str) -> dict[str, Any] | None:
        number = self.parse_table_number(text)
        if number is None:
            return None
        table = self.table_by_number(number)
        if not table:
            return None

        existing = self.db.fetchone(
            """
            select s.*, m.numero as mesa_numero, m.nome as mesa_nome
            from sessoes_mesa s
            join mesas m on m.id = s.mesa_id
            where s.mesa_id = ? and s.cliente_whatsapp = ?
              and s.status in ('sessao_pendente', 'sessao_ativa', 'conta_solicitada')
            order by s.aberta_em desc
            limit 1
            """,
            (table["id"], remote_jid),
        )
        if existing:
            return existing

        session_id = new_id()
        now = utc_now()
        status = "sessao_ativa"
        with self.db.transaction() as conn:
            conn.execute(
                """
                insert into sessoes_mesa (
                  id, restaurante_id, unidade_id, mesa_id, cliente_whatsapp,
                  status, aberta_em, validada_em
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    table["restaurante_id"],
                    table["unidade_id"],
                    table["id"],
                    remote_jid,
                    status,
                    now,
                    now,
                ),
            )
            conn.execute("update mesas set status = 'sessao_ativa' where id = ?", (table["id"],))

        return self.active_session_for_whatsapp(remote_jid)

    def list_tables(self) -> list[dict[str, Any]]:
        return self.db.fetchall(
            """
            select m.*, count(s.id) as sessoes_abertas
            from mesas m
            left join sessoes_mesa s on s.mesa_id = m.id
              and s.status in ('sessao_pendente', 'sessao_ativa', 'conta_solicitada')
            group by m.id
            order by m.numero
            """
        )

    def close_session(self, session_id: str) -> None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        if not session:
            return
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                "update sessoes_mesa set status = 'sessao_fechada', fechada_em = ? where id = ?",
                (now, session_id),
            )
            conn.execute("update mesas set status = 'sessao_fechada' where id = ?", (session["mesa_id"],))

    def request_account_close(self, session_id: str) -> None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        if not session:
            return
        with self.db.transaction() as conn:
            conn.execute(
                "update sessoes_mesa set status = 'conta_solicitada' where id = ?",
                (session_id,),
            )
            conn.execute("update mesas set status = 'conta_solicitada' where id = ?", (session["mesa_id"],))
