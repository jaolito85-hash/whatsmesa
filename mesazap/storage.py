from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SQLITE_SCHEMA = """
create table if not exists restaurantes (
  id text primary key,
  nome text not null,
  slug text not null unique,
  telefone_whatsapp text,
  timezone text not null default 'America/Sao_Paulo',
  ativo integer not null default 1,
  criado_em text not null
);

create table if not exists unidades (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  nome text not null,
  endereco text,
  cidade text,
  ativo integer not null default 1
);

create table if not exists mesas (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  unidade_id text not null references unidades(id) on delete cascade,
  numero integer not null,
  nome text not null,
  status text not null default 'mesa_livre',
  qr_token_atual text not null unique,
  ativa integer not null default 1,
  unique(restaurante_id, unidade_id, numero)
);

create table if not exists sessoes_mesa (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  unidade_id text not null references unidades(id) on delete cascade,
  mesa_id text not null references mesas(id) on delete cascade,
  cliente_whatsapp text not null,
  status text not null,
  aberta_por_funcionario_id text,
  validada_por_funcionario_id text,
  aberta_em text not null,
  validada_em text,
  fechada_em text
);

create table if not exists produtos (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  nome text not null,
  descricao text,
  preco real not null,
  categoria text not null,
  setor text not null,
  ativo integer not null default 1,
  disponivel integer not null default 1
);

create table if not exists produto_aliases (
  id text primary key,
  produto_id text not null references produtos(id) on delete cascade,
  alias text not null
);

create table if not exists pedidos (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  unidade_id text not null references unidades(id) on delete cascade,
  mesa_id text not null references mesas(id) on delete cascade,
  sessao_mesa_id text not null references sessoes_mesa(id) on delete cascade,
  cliente_whatsapp text not null,
  status text not null,
  total_estimado real not null default 0,
  texto_original text not null,
  origem text not null,
  criado_em text not null,
  confirmado_em text
);

create table if not exists pedido_itens (
  id text primary key,
  pedido_id text not null references pedidos(id) on delete cascade,
  produto_id text not null references produtos(id),
  nome_snapshot text not null,
  quantidade integer not null,
  preco_unitario_snapshot real not null,
  setor text not null,
  observacoes text,
  status text not null default 'novo'
);

create table if not exists solicitacoes_salao (
  id text primary key,
  restaurante_id text not null references restaurantes(id) on delete cascade,
  mesa_id text not null references mesas(id) on delete cascade,
  sessao_mesa_id text not null references sessoes_mesa(id) on delete cascade,
  tipo text not null,
  descricao text not null,
  setor text not null default 'salao',
  status text not null default 'nova',
  criada_em text not null,
  concluida_em text
);

create table if not exists mensagens_whatsapp (
  id text primary key,
  restaurante_id text,
  message_id text not null unique,
  remote_jid text not null,
  mesa_id text,
  sessao_mesa_id text,
  tipo text not null,
  texto text,
  audio_url text,
  payload_bruto text,
  processada integer not null default 0,
  criada_em text not null
);

create table if not exists eventos_pedido (
  id text primary key,
  pedido_id text not null references pedidos(id) on delete cascade,
  tipo text not null,
  descricao text not null,
  criado_por text not null,
  criado_em text not null
);

create table if not exists billing_accounts (
  id text primary key,
  restaurante_id text not null unique references restaurantes(id) on delete cascade,
  status text not null default 'aguardando_setup',
  preco_por_pedido real not null default 1.97,
  setup_fee real not null default 99.00,
  setup_fee_paid_em text,
  moeda text not null default 'BRL',
  criado_em text not null
);

create table if not exists faturas (
  id text primary key,
  billing_account_id text not null references billing_accounts(id) on delete cascade,
  periodo_ano_mes text not null,
  qtd_pedidos integer not null default 0,
  valor_pedidos real not null default 0,
  valor_setup real not null default 0,
  valor_total real not null,
  moeda text not null default 'BRL',
  status text not null default 'aberta',
  gerada_em text not null,
  vence_em text,
  paga_em text,
  unique(billing_account_id, periodo_ano_mes)
);

create table if not exists billing_events (
  id text primary key,
  billing_account_id text not null references billing_accounts(id) on delete cascade,
  tipo text not null,
  pedido_id text references pedidos(id) on delete set null,
  valor real not null,
  moeda text not null default 'BRL',
  periodo_ano_mes text not null,
  status_cobranca text not null default 'pendente',
  fatura_id text references faturas(id) on delete set null,
  criado_em text not null
);

create index if not exists mesas_status_idx on mesas(status);
create index if not exists sessoes_mesa_mesa_status_idx on sessoes_mesa(mesa_id, status);
create index if not exists sessoes_mesa_whatsapp_status_idx on sessoes_mesa(cliente_whatsapp, status);
create index if not exists produtos_restaurante_ativo_idx on produtos(restaurante_id, ativo, disponivel);
create index if not exists produto_aliases_alias_idx on produto_aliases(alias);
create index if not exists pedidos_sessao_status_idx on pedidos(sessao_mesa_id, status);
create index if not exists pedido_itens_setor_status_idx on pedido_itens(setor, status);
create index if not exists solicitacoes_setor_status_idx on solicitacoes_salao(setor, status);
create index if not exists mensagens_remote_jid_idx on mensagens_whatsapp(remote_jid);
create unique index if not exists billing_events_pedido_unq on billing_events(pedido_id) where pedido_id is not null and tipo = 'pedido_confirmado';
create index if not exists billing_events_account_periodo_idx on billing_events(billing_account_id, periodo_ano_mes, status_cobranca);
create index if not exists faturas_account_periodo_idx on faturas(billing_account_id, periodo_ano_mes);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        conn.execute("pragma busy_timeout = 5000")
        conn.execute("pragma journal_mode = wal")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SQLITE_SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, tuple(params))

    def message_exists(self, message_id: str) -> bool:
        row = self.fetchone(
            "select id from mensagens_whatsapp where message_id = ?",
            (message_id,),
        )
        return row is not None

    def record_message(
        self,
        *,
        message_id: str,
        remote_jid: str,
        tipo: str,
        texto: str | None,
        audio_url: str | None,
        payload: dict[str, Any],
        restaurante_id: str | None = None,
        mesa_id: str | None = None,
        sessao_mesa_id: str | None = None,
        processada: bool = False,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                insert or ignore into mensagens_whatsapp (
                  id, restaurante_id, message_id, remote_jid, mesa_id,
                  sessao_mesa_id, tipo, texto, audio_url, payload_bruto,
                  processada, criada_em
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    restaurante_id,
                    message_id,
                    remote_jid,
                    mesa_id,
                    sessao_mesa_id,
                    tipo,
                    texto,
                    audio_url,
                    json.dumps(payload, ensure_ascii=True),
                    1 if processada else 0,
                    utc_now(),
                ),
            )

    def mark_message_processed(
        self,
        message_id: str,
        *,
        restaurante_id: str | None,
        mesa_id: str | None,
        sessao_mesa_id: str | None,
    ) -> None:
        self.execute(
            """
            update mensagens_whatsapp
            set restaurante_id = ?, mesa_id = ?, sessao_mesa_id = ?, processada = 1
            where message_id = ?
            """,
            (restaurante_id, mesa_id, sessao_mesa_id, message_id),
        )

    def seed_demo(self) -> None:
        if self.fetchone("select id from restaurantes limit 1"):
            self.ensure_multilingual_demo_aliases()
            return

        now = utc_now()
        restaurante_id = new_id()
        unidade_id = new_id()

        products = [
            ("Corona long neck", "Cerveja long neck 330ml", 14.0, "cerveja", "bar", ["corona", "coronas", "cerveja corona", "corona beer", "cerveza corona"]),
            ("Brahma 600ml", "Garrafa 600ml", 13.0, "cerveja", "bar", ["brahma 600", "brahma 600ml", "garrafa de brahma", "brahma bottle", "botella de brahma"]),
            ("Brahma lata", "Lata 350ml", 7.0, "cerveja", "bar", ["brahma lata", "lata de brahma", "brahma can", "can of brahma"]),
            ("Caipirinha", "Limao, cachaca e acucar", 18.0, "drink", "bar", ["caipirinha", "caipi"]),
            ("Agua sem gas", "Garrafa 500ml", 5.0, "bebida", "bar", ["agua", "agua sem gas", "water", "still water", "agua sin gas"]),
            ("Refrigerante lata", "Coca, Guarana ou Sprite", 7.0, "bebida", "bar", ["refri", "refrigerante", "coca", "guarana", "soda", "soft drink", "refresco", "gaseosa"]),
            ("Porcao de batata frita", "Batata frita crocante", 32.0, "porcao", "cozinha", ["batata", "batata frita", "fritas", "porcao de batata", "fries", "french fries", "chips", "portion of fries", "papas fritas", "patatas fritas"]),
            ("Isca de frango", "Porcao com molho da casa", 38.0, "porcao", "cozinha", ["isca de frango", "frango", "porcao de frango", "chicken strips", "chicken bites", "tiras de pollo"]),
            ("Picanha acebolada", "Prato executivo", 54.0, "prato", "cozinha", ["picanha", "picanha acebolada", "picanha with onions"]),
            ("Pudim", "Sobremesa da casa", 12.0, "sobremesa", "cozinha", ["pudim", "sobremesa pudim", "flan", "pudding", "pudin"]),
        ]

        with self.transaction() as conn:
            conn.execute(
                """
                insert into restaurantes (id, nome, slug, telefone_whatsapp, timezone, ativo, criado_em)
                values (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    restaurante_id,
                    "MesaZap Demo",
                    "mesazap-demo",
                    "5500000000000",
                    "America/Sao_Paulo",
                    now,
                ),
            )
            conn.execute(
                """
                insert into unidades (id, restaurante_id, nome, endereco, cidade, ativo)
                values (?, ?, ?, ?, ?, 1)
                """,
                (unidade_id, restaurante_id, "Unidade Piloto", "Rua do MVP, 12", "Sao Paulo"),
            )
            conn.execute(
                """
                insert into billing_accounts (
                  id, restaurante_id, status, preco_por_pedido, setup_fee,
                  setup_fee_paid_em, moeda, criado_em
                ) values (?, ?, 'ativo', 1.97, 99.00, ?, 'BRL', ?)
                """,
                (new_id(), restaurante_id, now, now),
            )

            for number in range(1, 13):
                conn.execute(
                    """
                    insert into mesas (
                      id, restaurante_id, unidade_id, numero, nome,
                      status, qr_token_atual, ativa
                    ) values (?, ?, ?, ?, ?, 'mesa_ocupada', ?, 1)
                    """,
                    (
                        new_id(),
                        restaurante_id,
                        unidade_id,
                        number,
                        f"Mesa {number}",
                        f"mesa-{number:02d}-demo-token",
                    ),
                )

            for name, description, price, category, sector, aliases in products:
                product_id = new_id()
                conn.execute(
                    """
                    insert into produtos (
                      id, restaurante_id, nome, descricao, preco,
                      categoria, setor, ativo, disponivel
                    ) values (?, ?, ?, ?, ?, ?, ?, 1, 1)
                    """,
                    (product_id, restaurante_id, name, description, price, category, sector),
                )
                conn.execute(
                    "insert into produto_aliases (id, produto_id, alias) values (?, ?, ?)",
                    (new_id(), product_id, name),
                )
                for alias in aliases:
                    conn.execute(
                        "insert into produto_aliases (id, produto_id, alias) values (?, ?, ?)",
                        (new_id(), product_id, alias),
                    )

            brahma_products = conn.execute(
                "select id from produtos where nome like 'Brahma%'"
            ).fetchall()
            for row in brahma_products:
                conn.execute(
                    "insert into produto_aliases (id, produto_id, alias) values (?, ?, ?)",
                    (new_id(), row["id"], "brahma"),
                )

        self.ensure_multilingual_demo_aliases()

    def ensure_multilingual_demo_aliases(self) -> None:
        aliases_by_name = {
            "Corona long neck": ["coronas", "corona beer", "cerveza corona"],
            "Brahma 600ml": ["brahma bottle", "botella de brahma"],
            "Brahma lata": ["brahma can", "can of brahma"],
            "Agua sem gas": ["water", "still water", "agua sin gas"],
            "Refrigerante lata": ["soda", "soft drink", "refresco", "gaseosa"],
            "Porcao de batata frita": [
                "fries",
                "french fries",
                "chips",
                "portion of fries",
                "papas fritas",
                "patatas fritas",
            ],
            "Isca de frango": ["chicken strips", "chicken bites", "tiras de pollo"],
            "Picanha acebolada": ["picanha with onions"],
            "Pudim": ["flan", "pudding", "pudin"],
        }
        products = self.fetchall("select id, nome from produtos")
        with self.transaction() as conn:
            for product in products:
                aliases = aliases_by_name.get(product["nome"], [])
                if not aliases:
                    continue
                existing = {
                    row["alias"].lower()
                    for row in conn.execute(
                        "select alias from produto_aliases where produto_id = ?",
                        (product["id"],),
                    ).fetchall()
                }
                for alias in aliases:
                    if alias.lower() in existing:
                        continue
                    conn.execute(
                        "insert into produto_aliases (id, produto_id, alias) values (?, ?, ?)",
                        (new_id(), product["id"], alias),
                    )
