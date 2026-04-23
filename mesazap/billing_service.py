from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .storage import Database, new_id, utc_now


DEFAULT_PRICE_PER_ORDER = 1.97
DEFAULT_SETUP_FEE = 99.00
DEFAULT_CURRENCY = "BRL"

ACCOUNT_STATUSES = ("aguardando_setup", "ativo", "suspenso", "cancelado")


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


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
                DEFAULT_PRICE_PER_ORDER,
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

    def record_confirmed_order(
        self,
        *,
        restaurante_id: str,
        pedido_id: str,
    ) -> dict[str, Any] | None:
        account = self.account_for_restaurant(restaurante_id)
        if account["status"] != "ativo":
            return None

        existing = self.db.fetchone(
            """
            select id
            from billing_events
            where pedido_id = ? and tipo = 'pedido_confirmado'
            """,
            (pedido_id,),
        )
        if existing:
            return None

        event_id = new_id()
        self.db.execute(
            """
            insert into billing_events (
              id, billing_account_id, tipo, pedido_id, valor, moeda,
              periodo_ano_mes, status_cobranca, criado_em
            ) values (?, ?, 'pedido_confirmado', ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                event_id,
                account["id"],
                pedido_id,
                account["preco_por_pedido"],
                account["moeda"],
                current_period(),
                utc_now(),
            ),
        )
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
              and tipo = 'pedido_confirmado'
              and periodo_ano_mes = ?
            """,
            (account["id"], periodo),
        )
        return {
            "account": account,
            "periodo": periodo,
            "qtd_pedidos": int(stats["qtd"]) if stats else 0,
            "valor_pedidos": float(stats["total"]) if stats else 0.0,
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

        existing = self.db.fetchone(
            "select * from faturas where billing_account_id = ? and periodo_ano_mes = ?",
            (account["id"], periodo),
        )
        if existing:
            return existing

        events = self.db.fetchall(
            """
            select id, tipo, valor
            from billing_events
            where billing_account_id = ?
              and periodo_ano_mes = ?
              and status_cobranca = 'pendente'
            """,
            (account["id"], periodo),
        )

        qtd_pedidos = sum(1 for e in events if e["tipo"] == "pedido_confirmado")
        valor_pedidos = sum(float(e["valor"]) for e in events if e["tipo"] == "pedido_confirmado")
        valor_setup = sum(float(e["valor"]) for e in events if e["tipo"] == "setup")
        valor_total = valor_pedidos + valor_setup

        fatura_id = new_id()
        now = utc_now()
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

        return self.db.fetchone("select * from faturas where id = ?", (fatura_id,))

    def mark_invoice_paid(self, fatura_id: str) -> dict[str, Any]:
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
