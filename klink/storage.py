from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Slug usado para o restaurante de demonstração (estado "ainda não configurado").
DEMO_SLUG = "klink-demo"


def slugify(value: str) -> str:
    """Transforma um nome em um slug simples (sem acentos, minúsculo, com hífens)."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "restaurante"


SQLITE_SCHEMA = """
create table if not exists restaurantes (
  id text primary key,
  nome text not null,
  slug text not null unique,
  telefone_whatsapp text,
  whatsapp_equipe text,
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
  fechada_em text,
  ultima_atividade_em text
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
  preco_por_pedido real not null default 3.97,
  setup_fee real not null default 147.00,
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
  sessao_mesa_id text references sessoes_mesa(id) on delete set null,
  mesa_giro text,
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
create index if not exists pedido_itens_setor_status_idx on pedido_itens(setor, status);
create index if not exists solicitacoes_setor_status_idx on solicitacoes_salao(setor, status);
create index if not exists mensagens_remote_jid_idx on mensagens_whatsapp(remote_jid);
create index if not exists billing_events_account_periodo_idx on billing_events(billing_account_id, periodo_ano_mes, status_cobranca);
create index if not exists faturas_account_periodo_idx on faturas(billing_account_id, periodo_ano_mes);

create table if not exists app_estado (
  chave text primary key,
  valor text not null,
  atualizado_em text not null
);

create table if not exists whatsapp_send_log (
  id text primary key,
  restaurante_id text,
  remote_jid text,
  sucesso integer not null default 1,
  erro text,
  criado_em text not null
);

create index if not exists whatsapp_send_log_criado_idx on whatsapp_send_log(criado_em);

-- Leads do agente vendedor (SDR): quem chega pelo tráfego pago no WhatsApp
-- comercial. Uma linha por número de WhatsApp; o histórico fica em sdr_mensagens.
create table if not exists sdr_leads (
  remote_jid text primary key,
  nome text,
  status text not null default 'conversando',
  resumo text,
  notificado_em text,
  criado_em text not null,
  atualizado_em text not null
);

create table if not exists sdr_mensagens (
  id text primary key,
  remote_jid text not null,
  autor text not null,            -- 'lead' ou 'agente'
  texto text not null,
  criado_em text not null
);

create index if not exists sdr_mensagens_lead_idx on sdr_mensagens(remote_jid, criado_em);
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
            self._apply_migrations(conn)

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        # restaurantes
        cols_rest = {row[1] for row in conn.execute("pragma table_info(restaurantes)").fetchall()}
        if "whatsapp_equipe" not in cols_rest:
            # WhatsApp da equipe (cozinha/garçom): para onde a comanda é enviada
            # quando o cliente confirma um pedido. Pode ser número ou grupo.
            conn.execute("alter table restaurantes add column whatsapp_equipe text")

        # sessoes_mesa
        cols_sessao = {row[1] for row in conn.execute("pragma table_info(sessoes_mesa)").fetchall()}
        if "ultima_atividade_em" not in cols_sessao:
            conn.execute("alter table sessoes_mesa add column ultima_atividade_em text")
            conn.execute(
                "update sessoes_mesa set ultima_atividade_em = coalesce(validada_em, aberta_em) where ultima_atividade_em is null"
            )
        
        # pedidos
        cols_pedidos = {row[1] for row in conn.execute("pragma table_info(pedidos)").fetchall()}
        if "sessao_mesa_id" not in cols_pedidos:
            conn.execute("alter table pedidos add column sessao_mesa_id text references sessoes_mesa(id) on delete cascade")
        
        # solicitacoes_salao
        cols_solicitacoes = {row[1] for row in conn.execute("pragma table_info(solicitacoes_salao)").fetchall()}
        if "sessao_mesa_id" not in cols_solicitacoes:
            conn.execute("alter table solicitacoes_salao add column sessao_mesa_id text references sessoes_mesa(id) on delete cascade")
            
        # mensagens_whatsapp
        cols_mensagens = {row[1] for row in conn.execute("pragma table_info(mensagens_whatsapp)").fetchall()}
        if "sessao_mesa_id" not in cols_mensagens:
            conn.execute("alter table mensagens_whatsapp add column sessao_mesa_id text")

        # billing_events
        cols_events = {row[1] for row in conn.execute("pragma table_info(billing_events)").fetchall()}
        if "sessao_mesa_id" not in cols_events:
            conn.execute("alter table billing_events add column sessao_mesa_id text references sessoes_mesa(id) on delete set null")
        if "mesa_giro" not in cols_events:
            # Identificador do "giro" da mesa (mesa_id:token). Garante UMA cobrança
            # por ocupação física da mesa, mesmo com vários celulares pedindo nela.
            conn.execute("alter table billing_events add column mesa_giro text")
        
        # Criar indices que dependem das colunas migradas
        try:
            conn.execute("create index if not exists pedidos_sessao_status_idx on pedidos(sessao_mesa_id, status)")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("create unique index if not exists billing_events_pedido_unq on billing_events(pedido_id) where pedido_id is not null and tipo = 'pedido_confirmado'")
        except sqlite3.OperationalError:
            pass
            
        try:
            conn.execute("create unique index if not exists billing_events_sessao_unq on billing_events(sessao_mesa_id) where sessao_mesa_id is not null and tipo = 'mesa_aberta'")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("create unique index if not exists billing_events_giro_unq on billing_events(mesa_giro) where mesa_giro is not null and tipo = 'mesa_aberta'")
        except sqlite3.OperationalError:
            pass

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

    def update_restaurant(
        self,
        restaurante_id: str,
        *,
        nome: str | None = None,
        telefone_whatsapp: str | None = None,
        whatsapp_equipe: str | None = None,
    ) -> None:
        """Atualiza dados editáveis do restaurante (nome e WhatsApps)."""
        sets: list[str] = []
        params: list[Any] = []
        if nome is not None:
            sets.append("nome = ?")
            params.append(nome)
            # Ao definir um nome real, saímos do estado "demo" gerando um slug próprio.
            sets.append("slug = ?")
            params.append(slugify(nome))
        if telefone_whatsapp is not None:
            sets.append("telefone_whatsapp = ?")
            params.append(telefone_whatsapp)
        if whatsapp_equipe is not None:
            sets.append("whatsapp_equipe = ?")
            params.append(whatsapp_equipe)
        if not sets:
            return
        params.append(restaurante_id)
        self.execute(
            f"update restaurantes set {', '.join(sets)} where id = ?",
            params,
        )

    # ----- Mesas (cadastro do salão) -----

    def primary_unit_for(self, restaurante_id: str) -> dict[str, Any] | None:
        return self.fetchone(
            "select * from unidades where restaurante_id = ? and ativo = 1 limit 1",
            (restaurante_id,),
        )

    def create_table(
        self,
        restaurante_id: str,
        unidade_id: str,
        *,
        numero: int,
        nome: str = "",
    ) -> str | None:
        """Cria a mesa (ou reativa uma desativada com o mesmo número).

        Devolve o id da mesa criada/reativada, ou None se já existe mesa ATIVA
        com esse número. Reativar mantém o id antigo, então um QR impresso da
        mesa volta a funcionar.
        """
        nome_limpo = (nome or "").strip()
        existing = self.fetchone(
            "select id, ativa from mesas where restaurante_id = ? and unidade_id = ? and numero = ?",
            (restaurante_id, unidade_id, numero),
        )
        if existing and existing["ativa"]:
            return None
        if existing:
            # Reativação preserva o nome antigo ("Varanda 3") a menos que um nome
            # novo tenha sido informado explicitamente.
            self.execute(
                """
                update mesas
                set ativa = 1, nome = coalesce(nullif(?, ''), nome),
                    status = 'mesa_livre', qr_token_atual = ?
                where id = ?
                """,
                (nome_limpo, new_id(), existing["id"]),
            )
            return existing["id"]
        mesa_id = new_id()
        try:
            self.execute(
                """
                insert into mesas (
                  id, restaurante_id, unidade_id, numero, nome,
                  status, qr_token_atual, ativa
                ) values (?, ?, ?, ?, ?, 'mesa_livre', ?, 1)
                """,
                (
                    mesa_id,
                    restaurante_id,
                    unidade_id,
                    numero,
                    nome_limpo or f"Mesa {numero}",
                    new_id(),
                ),
            )
        except sqlite3.IntegrityError:
            # Corrida (duplo clique): outra requisição criou a mesma mesa entre o
            # select e o insert. A constraint unique protege; tratamos como
            # "já existe" em vez de estourar 500.
            return None
        return mesa_id

    def rename_table(self, mesa_id: str, nome: str) -> None:
        self.execute("update mesas set nome = ? where id = ?", (nome.strip(), mesa_id))

    # ----- Cardápio (produtos + apelidos) -----

    def _set_product_aliases(
        self, conn: sqlite3.Connection, produto_id: str, aliases: Iterable[str]
    ) -> None:
        conn.execute("delete from produto_aliases where produto_id = ?", (produto_id,))
        vistos: set[str] = set()
        for alias in aliases or []:
            limpo = (alias or "").strip()
            chave = limpo.lower()
            if not limpo or chave in vistos:
                continue
            vistos.add(chave)
            conn.execute(
                "insert into produto_aliases (id, produto_id, alias) values (?, ?, ?)",
                (new_id(), produto_id, limpo),
            )

    def create_product(
        self,
        restaurante_id: str,
        *,
        nome: str,
        preco: float,
        setor: str,
        categoria: str = "",
        descricao: str = "",
        disponivel: bool = True,
        aliases: Iterable[str] = (),
    ) -> str:
        produto_id = new_id()
        with self.transaction() as conn:
            conn.execute(
                """
                insert into produtos (
                  id, restaurante_id, nome, descricao, preco, categoria, setor,
                  ativo, disponivel
                ) values (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    produto_id,
                    restaurante_id,
                    nome,
                    descricao,
                    preco,
                    categoria or "geral",
                    setor,
                    1 if disponivel else 0,
                ),
            )
            self._set_product_aliases(conn, produto_id, aliases)
        return produto_id

    def update_product(
        self,
        produto_id: str,
        *,
        nome: str,
        preco: float,
        setor: str,
        categoria: str = "",
        descricao: str = "",
        disponivel: bool = True,
        aliases: Iterable[str] = (),
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                update produtos
                set nome = ?, descricao = ?, preco = ?, categoria = ?, setor = ?,
                    disponivel = ?
                where id = ?
                """,
                (
                    nome,
                    descricao,
                    preco,
                    categoria or "geral",
                    setor,
                    1 if disponivel else 0,
                    produto_id,
                ),
            )
            self._set_product_aliases(conn, produto_id, aliases)

    def deactivate_product(self, produto_id: str) -> None:
        # Soft delete: some do cardápio sem apagar o histórico de pedidos.
        self.execute("update produtos set ativo = 0 where id = ?", (produto_id,))

    def product_belongs_to(self, restaurante_id: str, produto_id: str) -> bool:
        row = self.fetchone(
            "select id from produtos where id = ? and restaurante_id = ? and ativo = 1",
            (produto_id, restaurante_id),
        )
        return row is not None

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
    ) -> bool:
        """Grava a mensagem. Devolve False se o message_id já existia.

        O retorno é o portão anti-duplicata do webhook: 'insert or ignore' com
        índice único é atômico — duas entregas simultâneas da mesma mensagem
        nunca processam duas vezes (o antigo check-then-insert tinha janela).
        """
        with self.transaction() as conn:
            cursor = conn.execute(
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
        return cursor.rowcount > 0

    def record_whatsapp_send(
        self,
        *,
        remote_jid: str,
        sucesso: bool,
        erro: str | None = None,
        restaurante_id: str | None = None,
    ) -> None:
        self.execute(
            """
            insert into whatsapp_send_log (
              id, restaurante_id, remote_jid, sucesso, erro, criado_em
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (new_id(), restaurante_id, remote_jid, 1 if sucesso else 0, erro, utc_now()),
        )

    def count_whatsapp_sends_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.fetchone(
            "select count(*) as total from whatsapp_send_log where substr(criado_em, 1, 10) = ?",
            (today,),
        )
        return int(row["total"]) if row else 0

    def set_estado(self, chave: str, valor: str) -> None:
        # Estado operacional do app (ex.: última situação da conexão do WhatsApp
        # reportada pela Evolution). Chave-valor simples, sobrevive a restart.
        self.execute(
            """
            insert into app_estado (chave, valor, atualizado_em) values (?, ?, ?)
            on conflict(chave) do update
            set valor = excluded.valor, atualizado_em = excluded.atualizado_em
            """,
            (chave, valor, utc_now()),
        )

    def get_estado(self, chave: str) -> dict[str, Any] | None:
        return self.fetchone("select * from app_estado where chave = ?", (chave,))

    # ----- Agente SDR (leads do tráfego pago) -----

    def sdr_get_lead(self, remote_jid: str) -> dict[str, Any] | None:
        return self.fetchone("select * from sdr_leads where remote_jid = ?", (remote_jid,))

    def sdr_ensure_lead(self, remote_jid: str, nome: str | None = None) -> dict[str, Any]:
        """Garante que o lead existe (cria na primeira mensagem) e devolve a linha."""
        existing = self.sdr_get_lead(remote_jid)
        if existing:
            # Preenche o nome se ainda não tínhamos e agora chegou (ex.: pushName).
            if nome and not existing.get("nome"):
                self.execute(
                    "update sdr_leads set nome = ?, atualizado_em = ? where remote_jid = ?",
                    (nome, utc_now(), remote_jid),
                )
                existing["nome"] = nome
            return existing
        now = utc_now()
        self.execute(
            """
            insert into sdr_leads (remote_jid, nome, status, criado_em, atualizado_em)
            values (?, ?, 'conversando', ?, ?)
            """,
            (remote_jid, nome, now, now),
        )
        return self.sdr_get_lead(remote_jid)  # type: ignore[return-value]

    def sdr_add_message(self, remote_jid: str, autor: str, texto: str) -> None:
        """Guarda uma mensagem da conversa. autor = 'lead' ou 'agente'."""
        self.execute(
            "insert into sdr_mensagens (id, remote_jid, autor, texto, criado_em) values (?, ?, ?, ?, ?)",
            (new_id(), remote_jid, autor, texto, utc_now()),
        )
        self.execute(
            "update sdr_leads set atualizado_em = ? where remote_jid = ?",
            (utc_now(), remote_jid),
        )

    def sdr_history(self, remote_jid: str, limit: int = 20) -> list[dict[str, Any]]:
        """Últimas mensagens da conversa, em ordem cronológica (mais antiga primeiro)."""
        rows = self.fetchall(
            """
            select autor, texto, criado_em from sdr_mensagens
            where remote_jid = ?
            order by criado_em desc
            limit ?
            """,
            (remote_jid, limit),
        )
        return list(reversed(rows))

    def sdr_mark_notified(self, remote_jid: str, resumo: str | None = None) -> None:
        """Marca que o João já foi avisado deste lead (evita avisar de novo)."""
        now = utc_now()
        self.execute(
            """
            update sdr_leads
            set status = 'qualificado', notificado_em = ?, resumo = coalesce(?, resumo),
                atualizado_em = ?
            where remote_jid = ?
            """,
            (now, resumo, now, remote_jid),
        )

    def sdr_update_nome(self, remote_jid: str, nome: str) -> None:
        self.execute(
            "update sdr_leads set nome = ?, atualizado_em = ? where remote_jid = ?",
            (nome, utc_now(), remote_jid),
        )

    def last_inbound_message_at(self) -> str | None:
        row = self.fetchone(
            "select max(criada_em) as ultima from mensagens_whatsapp"
        )
        return row["ultima"] if row else None

    def count_active_sessions(self) -> int:
        row = self.fetchone(
            """
            select count(*) as total from sessoes_mesa
            where status in ('sessao_pendente', 'sessao_ativa', 'conta_solicitada')
            """
        )
        return int(row["total"]) if row else 0

    def count_pending_sessions(self) -> int:
        row = self.fetchone(
            "select count(*) as total from sessoes_mesa where status = 'sessao_pendente'"
        )
        return int(row["total"]) if row else 0

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

    def migrate_legacy_data(self) -> None:
        """Corrige dados gravados por versões antigas. Idempotente, roda no boot.

        - Renomeia o restaurante demo "MesaZap Demo" -> "Klink Demo".
        - Atualiza o preço do modelo antigo (1,97/pedido) para o atual
          (3,97 por mesa aberta). Só afeta linhas com os valores legados conhecidos,
          então é seguro rodar em todo boot.
        """
        self.execute(
            "update restaurantes set nome = 'Klink Demo' where nome = 'MesaZap Demo'"
        )
        self.execute(
            "update restaurantes set slug = ? where slug = 'mesazap-demo'", (DEMO_SLUG,)
        )
        self.execute(
            "update billing_accounts set preco_por_pedido = 3.97 "
            "where preco_por_pedido = 1.97"
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
                    "Klink Demo",
                    "klink-demo",
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
                ) values (?, ?, 'ativo', 3.97, 147.00, ?, 'BRL', ?)
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
