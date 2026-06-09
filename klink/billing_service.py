from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from .storage import Database, new_id, utc_now


DEFAULT_PRICE_PER_SESSION = 3.97
DEFAULT_SETUP_FEE = 147.00
DEFAULT_CURRENCY = "BRL"

ACCOUNT_STATUSES = ("aguardando_setup", "ativo", "suspenso", "cancelado")

_CENTS = Decimal("0.01")


def _billing_timezone():
    # O "mês" da fatura vira à meia-noite de Brasília, não às 21h (que era a
    # virada do mês em UTC) — evita mesa de fim de mês cair na fatura errada.
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Sao_Paulo")
    except Exception:  # pragma: no cover - sem tzdata instalado
        return timezone.utc


BILLING_TZ = _billing_timezone()


def money_round(value: Any) -> float:
    # Arredonda um valor monetario para 2 casas (centavos), meio-para-cima.
    # Evita exibir/gravar restos de ponto flutuante (ex.: 396.9999999999994).
    return float(Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP))


def money_sum(values: Iterable[Any]) -> float:
    # Soma valores monetarios em Decimal (sem erro de acumulacao de float) e
    # devolve o total ja arredondado em centavos.
    total = sum((Decimal(str(v)) for v in values), Decimal("0"))
    return float(total.quantize(_CENTS, rounding=ROUND_HALF_UP))


def current_period() -> str:
    return datetime.now(BILLING_TZ).strftime("%Y-%m")


class BillingService:
    def __init__(self, db: Database):
        self.db = db

    def account_for_restaurant(self, restaurante_id: str) -> dict[str, Any]:
        row = self.db.fetchone(
            "select * from billing_accounts where restaurante_id = ?",
            (restaurante_id,),
        )
        if row:
            return row
        self.db.execute(
            """
            insert into billing_accounts (
              id, restaurante_id, status, preco_por_pedido, setup_fee,
              moeda, criado_em
            ) values (?, ?, 'aguardando_setup', ?, ?, ?, ?)
            """,
            (
                new_id(),
                restaurante_id,
                DEFAULT_PRICE_PER_SESSION,
                DEFAULT_SETUP_FEE,
                DEFAULT_CURRENCY,
                utc_now(),
            ),
        )
        return self.db.fetchone(
            "select * from billing_accounts where restaurante_id = ?",
            (restaurante_id,),
        )

    def is_active(self, restaurante_id: str) -> bool:
        account = self.account_for_restaurant(restaurante_id)
        return account["status"] == "ativo"

    def mark_setup_paid(self, restaurante_id: str) -> dict[str, Any]:
        account = self.account_for_restaurant(restaurante_id)
        if account["setup_fee_paid_em"]:
            return account

        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                update billing_accounts
                set status = 'ativo', setup_fee_paid_em = ?
                where id = ?
                """,
                (now, account["id"]),
            )
            conn.execute(
                """
                insert into billing_events (
                   id, billing_account_id, tipo, valor, moeda,
                   periodo_ano_mes, status_cobranca, criado_em
                ) values (?, ?, 'setup', ?, ?, ?, 'pago', ?)
                """,
                (
                    new_id(),
                    account["id"],
                    account["setup_fee"],
                    account["moeda"],
                    current_period(),
                    now,
                ),
            )
        return self.account_for_restaurant(restaurante_id)

    def require_setup_if_unpaid(self, restaurante_id: str) -> dict[str, Any]:
        """Volta a conta para 'aguardando_setup' se os R$ 147 nunca foram
        registrados de verdade (nenhum evento 'setup' no histórico).

        A conta da demonstração nasce 'ativa' para o teste funcionar de
        primeira. Quando o restaurante deixa de ser demo (ganha nome real no
        onboarding), esta trava entra: o bot só atende depois do
        /admin/billing/setup-paid — que registra o evento e entra na fatura.
        Cliente que já pagou (evento existe) não é afetado por renomes futuros.
        """
        account = self.account_for_restaurant(restaurante_id)
        setup_event = self.db.fetchone(
            """
            select id from billing_events
            where billing_account_id = ? and tipo = 'setup'
            limit 1
            """,
            (account["id"],),
        )
        if setup_event:
            return account
        with self.db.transaction() as conn:
            conn.execute(
                """
                update billing_accounts
                set status = 'aguardando_setup', setup_fee_paid_em = null
                where id = ?
                """,
                (account["id"],),
            )
            # As mesas abertas na FASE DEMO (testes do fundador) não podem
            # entrar na primeira fatura do cliente — eram cortesia. Sem isto,
            # a varredura "<= periodo" da fatura cobraria os próprios testes.
            conn.execute(
                """
                update billing_events
                set status_cobranca = 'cancelado'
                where billing_account_id = ?
                  and tipo = 'mesa_aberta'
                  and status_cobranca = 'pendente'
                """,
                (account["id"],),
            )
        return self.account_for_restaurant(restaurante_id)

    def suspend(self, restaurante_id: str) -> dict[str, Any]:
        account = self.account_for_restaurant(restaurante_id)
        self.db.execute(
            "update billing_accounts set status = 'suspenso' where id = ?",
            (account["id"],),
        )
        return self.account_for_restaurant(restaurante_id)

    def reactivate(self, restaurante_id: str) -> dict[str, Any]:
        account = self.account_for_restaurant(restaurante_id)
        if not account["setup_fee_paid_em"]:
            raise ValueError("Conta sem setup pago nao pode ser reativada.")
        self.db.execute(
            "update billing_accounts set status = 'ativo' where id = ?",
            (account["id"],),
        )
        return self.account_for_restaurant(restaurante_id)

    def record_session_billing(
        self,
        *,
        restaurante_id: str,
        sessao_id: str,
        mesa_id: str | None = None,
        mesa_token: str | None = None,
    ) -> dict[str, Any] | None:
        account = self.account_for_restaurant(restaurante_id)
        if account["status"] != "ativo":
            return None

        # mesa_giro identifica a OCUPAÇÃO FÍSICA da mesa: o qr_token_atual da mesa
        # rotaciona quando ela fecha, então (mesa_id:token) vale do primeiro celular
        # que abre até o fechamento. Vários celulares na mesma mesa caem no MESMO
        # giro => UMA cobrança de R$ 3,97 — exatamente o "por mesa aberta" prometido
        # na venda (antes, 4 amigos escaneando o QR viravam 4 cobranças).
        # O chamador deve passar mesa_token capturado NA MESMA transação que criou
        # a sessão: reler aqui abriria janela para um "fechar mesa" simultâneo
        # rotacionar o token e o próximo giro sair de graça.
        mesa_giro = None
        if mesa_id and mesa_token:
            mesa_giro = f"{mesa_id}:{mesa_token}"
        elif mesa_id:
            mesa = self.db.fetchone(
                "select qr_token_atual from mesas where id = ?", (mesa_id,)
            )
            if mesa:
                mesa_giro = f"{mesa_id}:{mesa['qr_token_atual']}"

        event_id = new_id()
        # INSERT OR IGNORE + indices unicos parciais (sessao_mesa_id e mesa_giro,
        # where tipo='mesa_aberta') tornam esta operacao atomica e idempotente:
        # mensagem duplicada da Evolution OU segundo celular na mesma mesa = o
        # INSERT e ignorado em silencio, sem IntegrityError e sem cobranca dupla.
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                insert or ignore into billing_events (
                   id, billing_account_id, tipo, sessao_mesa_id, mesa_giro, valor,
                   moeda, periodo_ano_mes, status_cobranca, criado_em
                ) values (?, ?, 'mesa_aberta', ?, ?, ?, ?, ?, 'pendente', ?)
                """,
                (
                    event_id,
                    account["id"],
                    sessao_id,
                    mesa_giro,
                    account["preco_por_pedido"],
                    account["moeda"],
                    current_period(),
                    utc_now(),
                ),
            )
            inserted = cursor.rowcount > 0

        if not inserted:
            # Ja existia cobranca para esta sessao ou para este giro da mesa:
            # idempotente, nada a cobrar.
            return None
        return self.db.fetchone("select * from billing_events where id = ?", (event_id,))

    def usage_summary(
        self,
        restaurante_id: str,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        account = self.account_for_restaurant(restaurante_id)
        periodo = periodo or current_period()

        stats = self.db.fetchone(
            """
            select count(*) as qtd, coalesce(sum(valor), 0) as total
            from billing_events
            where billing_account_id = ?
              and tipo = 'mesa_aberta'
              and periodo_ano_mes = ?
            """,
            (account["id"], periodo),
        )
        return {
            "account": account,
            "periodo": periodo,
            "qtd_pedidos": int(stats["qtd"]) if stats else 0,
            "valor_pedidos": money_round(stats["total"]) if stats else 0.0,
            "preco_por_pedido": float(account["preco_por_pedido"]),
            "moeda": account["moeda"],
        }

    def generate_invoice(
        self,
        restaurante_id: str,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        account = self.account_for_restaurant(restaurante_id)
        periodo = periodo or current_period()
        # Período fora do formato AAAA-MM ("2026-1", "jan/26") quebraria a
        # comparação por texto e poderia gerar fatura duplicada do mesmo mês.
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periodo):
            raise ValueError(f"Periodo invalido: {periodo!r}. Use o formato AAAA-MM.")

        existing = self.db.fetchone(
            "select * from faturas where billing_account_id = ? and periodo_ano_mes = ?",
            (account["id"], periodo),
        )
        if existing:
            return existing

        # "<= periodo" (e não "="): varre também eventos PENDENTES de meses
        # anteriores — ex.: mesa aberta depois que a fatura daquele mês já
        # tinha sido gerada. Sem isso, esses eventos ficavam 'pendente' para
        # sempre e nunca eram cobrados.
        events = self.db.fetchall(
            """
            select id, tipo, valor
            from billing_events
            where billing_account_id = ?
              and periodo_ano_mes <= ?
              and status_cobranca = 'pendente'
            """,
            (account["id"], periodo),
        )

        qtd_pedidos = sum(1 for e in events if e["tipo"] == "mesa_aberta")
        valor_pedidos = money_sum(e["valor"] for e in events if e["tipo"] == "mesa_aberta")
        valor_setup = money_sum(e["valor"] for e in events if e["tipo"] == "setup")
        valor_total = money_round(valor_pedidos + valor_setup)

        fatura_id = new_id()
        now = utc_now()
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    insert into faturas (
                      id, billing_account_id, periodo_ano_mes, qtd_pedidos,
                      valor_pedidos, valor_setup, valor_total, moeda, status, gerada_em
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, 'aberta', ?)
                    """,
                    (
                        fatura_id,
                        account["id"],
                        periodo,
                        qtd_pedidos,
                        valor_pedidos,
                        valor_setup,
                        valor_total,
                        account["moeda"],
                        now,
                    ),
                )
                for event in events:
                    conn.execute(
                        """
                        update billing_events
                        set status_cobranca = 'faturado', fatura_id = ?
                        where id = ?
                        """,
                        (fatura_id, event["id"]),
                    )
        except sqlite3.IntegrityError:
            # Corrida: outra chamada criou a fatura do mesmo periodo (unique
            # billing_account_id + periodo_ano_mes). Idempotente: retorna a existente.
            return self.db.fetchone(
                "select * from faturas where billing_account_id = ? and periodo_ano_mes = ?",
                (account["id"], periodo),
            )

        return self.db.fetchone("select * from faturas where id = ?", (fatura_id,))

    def mark_invoice_paid(self, fatura_id: str) -> dict[str, Any]:
        fatura = self.db.fetchone("select * from faturas where id = ?", (fatura_id,))
        if not fatura or fatura["status"] == "paga":
            return fatura  # idempotente: fatura inexistente ou já paga
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                "update faturas set status = 'paga', paga_em = ? where id = ?",
                (now, fatura_id),
            )
            conn.execute(
                "update billing_events set status_cobranca = 'pago' where fatura_id = ?",
                (fatura_id,),
            )
        return self.db.fetchone("select * from faturas where id = ?", (fatura_id,))

    def list_invoices(self, restaurante_id: str) -> list[dict[str, Any]]:
        account = self.account_for_restaurant(restaurante_id)
        return self.db.fetchall(
            """
            select * from faturas
            where billing_account_id = ?
            order by periodo_ano_mes desc
            """,
            (account["id"],),
        )
