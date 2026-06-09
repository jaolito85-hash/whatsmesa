from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .storage import Database, new_id, utc_now
from .text_utils import normalize_text


ACTIVE_SESSION_STATUSES = ("sessao_pendente", "sessao_ativa", "conta_solicitada")
IDLE_TTL_HOURS = 6


class TableSessionService:
    def __init__(
        self,
        db: Database,
        billing: BillingService | None = None,
        idle_ttl_hours: int = IDLE_TTL_HOURS,
        require_validation: bool = False,
    ):
        self.db = db
        self.billing = billing
        self.idle_ttl_hours = idle_ttl_hours
        self.require_validation = require_validation

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

    def table_by_id(self, mesa_id: str) -> dict[str, Any] | None:
        # Identificador PERMANENTE da mesa, usado pelo QR impresso (que nunca muda).
        return self.db.fetchone(
            "select * from mesas where id = ? and ativa = 1",
            (mesa_id,),
        )

    def active_session_for_whatsapp(self, remote_jid: str) -> dict[str, Any] | None:
        self._expire_idle_sessions()
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        session = self.db.fetchone(
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
        if session:
            self._touch(session["id"])
        return session

    def activate_from_message(self, remote_jid: str, text: str) -> dict[str, Any] | None:
        number = self.parse_table_number(text)
        if number is None:
            return None
        table = self.table_by_number(number)
        if not table:
            return None

        self._expire_idle_sessions()

        existing = self.db.fetchone(
            f"""
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
            self._touch(existing["id"])
            return existing

        self._close_other_sessions_for_jid(remote_jid, table["id"])

        session_id = new_id()
        now = utc_now()
        if self.require_validation:
            status = "sessao_pendente"
            mesa_status = "sessao_pendente"
            validada_em = None
        else:
            status = "sessao_ativa"
            mesa_status = "sessao_ativa"
            validada_em = now
        with self.db.transaction() as conn:
            conn.execute(
                """
                insert into sessoes_mesa (
                  id, restaurante_id, unidade_id, mesa_id, cliente_whatsapp,
                  status, aberta_em, validada_em, ultima_atividade_em
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    table["restaurante_id"],
                    table["unidade_id"],
                    table["id"],
                    remote_jid,
                    status,
                    now,
                    validada_em,
                    now,
                ),
            )
            conn.execute("update mesas set status = ? where id = ?", (mesa_status, table["id"]))

        if not self.require_validation and self.billing:
            self.billing.record_session_billing(
                restaurante_id=table["restaurante_id"],
                sessao_id=session_id,
                mesa_id=table["id"],
            )

        return self.active_session_for_whatsapp(remote_jid)

    def list_pending_sessions(self) -> list[dict[str, Any]]:
        return self.db.fetchall(
            """
            select s.*, m.numero as mesa_numero, m.nome as mesa_nome
            from sessoes_mesa s
            join mesas m on m.id = s.mesa_id
            where s.status = 'sessao_pendente'
            order by s.aberta_em asc
            """
        )

    def validate_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        if not session or session["status"] != "sessao_pendente":
            return session
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                update sessoes_mesa
                set status = 'sessao_ativa', validada_em = ?, ultima_atividade_em = ?
                where id = ?
                """,
                (now, now, session_id),
            )
            conn.execute(
                "update mesas set status = 'sessao_ativa' where id = ?",
                (session["mesa_id"],),
            )
        
        if self.billing:
            self.billing.record_session_billing(
                restaurante_id=session["restaurante_id"],
                sessao_id=session_id,
                mesa_id=session["mesa_id"],
            )

        return self.db.fetchone(
            """
            select s.*, m.numero as mesa_numero, m.nome as mesa_nome
            from sessoes_mesa s
            join mesas m on m.id = s.mesa_id
            where s.id = ?
            """,
            (session_id,),
        )

    def reject_session(self, session_id: str) -> None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        # Só recusa sessão PENDENTE (ainda não validada/cobrada). Uma sessão já ativa foi
        # cobrada (R$/mesa); encerrá-la é via close_session, não reject — assim evitamos
        # cobrança "órfã" de uma mesa que o garçom rejeitou por engano.
        if not session or session["status"] != "sessao_pendente":
            return
        now = utc_now()
        new_token = new_id()
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        with self.db.transaction() as conn:
            conn.execute(
                "update sessoes_mesa set status = 'sessao_recusada', fechada_em = ? where id = ?",
                (now, session_id),
            )
            # Recusar um celular não pode liberar a mesa se outra sessão (de
            # outro celular) continua ativa nela.
            remaining = conn.execute(
                f"""
                select 1 from sessoes_mesa
                where mesa_id = ? and id != ? and status in ({placeholders})
                limit 1
                """,
                (session["mesa_id"], session_id, *ACTIVE_SESSION_STATUSES),
            ).fetchone()
            if not remaining:
                conn.execute(
                    "update mesas set status = 'mesa_livre', qr_token_atual = ? where id = ?",
                    (new_token, session["mesa_id"]),
                )

    def list_tables(self) -> list[dict[str, Any]]:
        return self.db.fetchall(
            """
            select m.*, count(s.id) as sessoes_abertas
            from mesas m
            left join sessoes_mesa s on s.mesa_id = m.id
              and s.status in ('sessao_pendente', 'sessao_ativa', 'conta_solicitada')
            where m.ativa = 1
            group by m.id
            order by m.numero
            """
        )

    def close_session(self, session_id: str) -> None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        if not session:
            return
        if session["status"] == "sessao_fechada":
            return
        now = utc_now()
        new_token = new_id()
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        with self.db.transaction() as conn:
            conn.execute(
                "update sessoes_mesa set status = 'sessao_fechada', fechada_em = ? where id = ?",
                (now, session_id),
            )
            # A mesa só fica livre (e o token do giro só rotaciona) quando a
            # ÚLTIMA sessão dela fecha. Antes, o primeiro amigo que fechava a
            # conta marcava a mesa como livre com os outros ainda pedindo nela.
            remaining = conn.execute(
                f"""
                select 1 from sessoes_mesa
                where mesa_id = ? and id != ? and status in ({placeholders})
                limit 1
                """,
                (session["mesa_id"], session_id, *ACTIVE_SESSION_STATUSES),
            ).fetchone()
            if not remaining:
                conn.execute(
                    "update mesas set status = 'mesa_livre', qr_token_atual = ? where id = ?",
                    (new_token, session["mesa_id"]),
                )

    def deactivate_table(self, mesa_id: str) -> bool:
        """Tira a mesa do salão (soft delete), só se não houver comanda aberta.

        A checagem e o update acontecem num único SQL: entre um "if" separado e
        o update, o webhook (outra thread) poderia abrir sessão na mesa — e a
        mesa sumiria do painel com cliente pedindo nela. Devolve False quando a
        mesa está em uso (ou não existe ativa).
        """
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"""
                update mesas
                set ativa = 0, status = 'mesa_livre'
                where id = ? and ativa = 1
                  and not exists (
                    select 1 from sessoes_mesa s
                    where s.mesa_id = mesas.id and s.status in ({placeholders})
                  )
                """,
                (mesa_id, *ACTIVE_SESSION_STATUSES),
            )
            return cursor.rowcount > 0

    def close_table(self, mesa_id: str) -> int:
        """Fecha TODAS as sessões ativas da mesa e a libera no painel.

        Botão manual do painel: cobre o caso mais comum no Brasil — o cliente
        paga no caixa e vai embora sem mandar "fecha a conta" no WhatsApp.
        Devolve quantas sessões foram fechadas.
        """
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATUSES)
        rows = self.db.fetchall(
            f"""
            select id from sessoes_mesa
            where mesa_id = ? and status in ({placeholders})
            """,
            (mesa_id, *ACTIVE_SESSION_STATUSES),
        )
        for row in rows:
            self.close_session(row["id"])
        if not rows:
            # Mesa marcada como ocupada sem nenhuma sessão ativa (estado herdado,
            # ex.: seed antigo): só libera o status no painel.
            self.db.execute(
                "update mesas set status = 'mesa_livre' where id = ?", (mesa_id,)
            )
        return len(rows)

    def request_account_close(self, session_id: str) -> None:
        session = self.db.fetchone("select * from sessoes_mesa where id = ?", (session_id,))
        if not session:
            return
        with self.db.transaction() as conn:
            conn.execute(
                "update sessoes_mesa set status = 'conta_solicitada', ultima_atividade_em = ? where id = ?",
                (utc_now(), session_id),
            )
            conn.execute("update mesas set status = 'conta_solicitada' where id = ?", (session["mesa_id"],))

    def _close_other_sessions_for_jid(self, remote_jid: str, current_table_id: str) -> None:
        rows = self.db.fetchall(
            f"""
            select id from sessoes_mesa
            where cliente_whatsapp = ?
              and mesa_id != ?
              and status in ({",".join("?" for _ in ACTIVE_SESSION_STATUSES)})
            """,
            (remote_jid, current_table_id, *ACTIVE_SESSION_STATUSES),
        )
        for row in rows:
            self.close_session(row["id"])

    def _expire_idle_sessions(self) -> None:
        if self.idle_ttl_hours <= 0:
            return
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self.idle_ttl_hours)
        ).isoformat(timespec="seconds")
        rows = self.db.fetchall(
            f"""
            select id from sessoes_mesa
            where status in ({",".join("?" for _ in ACTIVE_SESSION_STATUSES)})
              and coalesce(ultima_atividade_em, validada_em, aberta_em) < ?
            """,
            (*ACTIVE_SESSION_STATUSES, cutoff),
        )
        for row in rows:
            self.close_session(row["id"])

    def _touch(self, session_id: str) -> None:
        self.db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (utc_now(), session_id),
        )
