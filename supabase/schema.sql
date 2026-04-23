create extension if not exists pgcrypto;

create table if not exists public.restaurantes (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  slug text not null unique,
  telefone_whatsapp text,
  timezone text not null default 'America/Sao_Paulo',
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create table if not exists public.unidades (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  nome text not null,
  endereco text,
  cidade text,
  ativo boolean not null default true
);

create table if not exists public.mesas (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  unidade_id uuid not null references public.unidades(id) on delete cascade,
  numero integer not null,
  nome text not null,
  status text not null default 'mesa_livre'
    check (status in ('mesa_livre', 'mesa_ocupada', 'sessao_pendente', 'sessao_ativa', 'conta_solicitada', 'sessao_fechada')),
  qr_token_atual text not null unique,
  ativa boolean not null default true,
  unique (restaurante_id, unidade_id, numero)
);

create table if not exists public.sessoes_mesa (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  unidade_id uuid not null references public.unidades(id) on delete cascade,
  mesa_id uuid not null references public.mesas(id) on delete cascade,
  cliente_whatsapp text not null,
  status text not null
    check (status in ('sessao_pendente', 'sessao_ativa', 'conta_solicitada', 'sessao_fechada')),
  aberta_por_funcionario_id uuid,
  validada_por_funcionario_id uuid,
  aberta_em timestamptz not null default now(),
  validada_em timestamptz,
  fechada_em timestamptz
);

create table if not exists public.produtos (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  nome text not null,
  descricao text,
  preco numeric(10, 2) not null check (preco >= 0),
  categoria text not null,
  setor text not null check (setor in ('bar', 'cozinha', 'salao', 'caixa')),
  ativo boolean not null default true,
  disponivel boolean not null default true
);

create table if not exists public.produto_aliases (
  id uuid primary key default gen_random_uuid(),
  produto_id uuid not null references public.produtos(id) on delete cascade,
  alias text not null,
  unique (produto_id, alias)
);

create table if not exists public.pedidos (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  unidade_id uuid not null references public.unidades(id) on delete cascade,
  mesa_id uuid not null references public.mesas(id) on delete cascade,
  sessao_mesa_id uuid not null references public.sessoes_mesa(id) on delete cascade,
  cliente_whatsapp text not null,
  status text not null
    check (status in ('rascunho', 'aguardando_confirmacao_cliente', 'aguardando_validacao_mesa', 'enviado_setor', 'em_preparo', 'pronto', 'entregue', 'cancelado')),
  total_estimado numeric(10, 2) not null default 0,
  texto_original text not null,
  origem text not null default 'whatsapp',
  criado_em timestamptz not null default now(),
  confirmado_em timestamptz
);

create table if not exists public.pedido_itens (
  id uuid primary key default gen_random_uuid(),
  pedido_id uuid not null references public.pedidos(id) on delete cascade,
  produto_id uuid not null references public.produtos(id),
  nome_snapshot text not null,
  quantidade integer not null check (quantidade > 0),
  preco_unitario_snapshot numeric(10, 2) not null check (preco_unitario_snapshot >= 0),
  setor text not null check (setor in ('bar', 'cozinha', 'salao', 'caixa')),
  observacoes text,
  status text not null default 'novo'
    check (status in ('novo', 'em_preparo', 'pronto', 'entregue', 'cancelado'))
);

create table if not exists public.solicitacoes_salao (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null references public.restaurantes(id) on delete cascade,
  mesa_id uuid not null references public.mesas(id) on delete cascade,
  sessao_mesa_id uuid not null references public.sessoes_mesa(id) on delete cascade,
  tipo text not null
    check (tipo in ('chamar_garcom', 'guardanapo', 'talher', 'molho', 'limpeza', 'fechar_conta', 'outro')),
  descricao text not null,
  setor text not null default 'salao' check (setor in ('salao', 'caixa')),
  status text not null default 'nova'
    check (status in ('nova', 'em_atendimento', 'concluida', 'cancelada')),
  criada_em timestamptz not null default now(),
  concluida_em timestamptz
);

create table if not exists public.mensagens_whatsapp (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid references public.restaurantes(id) on delete cascade,
  message_id text not null unique,
  remote_jid text not null,
  mesa_id uuid references public.mesas(id) on delete set null,
  sessao_mesa_id uuid references public.sessoes_mesa(id) on delete set null,
  tipo text not null check (tipo in ('texto', 'audio')),
  texto text,
  audio_url text,
  payload_bruto jsonb not null default '{}'::jsonb,
  processada boolean not null default false,
  criada_em timestamptz not null default now()
);

create table if not exists public.eventos_pedido (
  id uuid primary key default gen_random_uuid(),
  pedido_id uuid not null references public.pedidos(id) on delete cascade,
  tipo text not null,
  descricao text not null,
  criado_por text not null,
  criado_em timestamptz not null default now()
);

create table if not exists public.billing_accounts (
  id uuid primary key default gen_random_uuid(),
  restaurante_id uuid not null unique references public.restaurantes(id) on delete cascade,
  status text not null default 'aguardando_setup'
    check (status in ('aguardando_setup', 'ativo', 'suspenso', 'cancelado')),
  preco_por_pedido numeric(10, 2) not null default 1.97 check (preco_por_pedido >= 0),
  setup_fee numeric(10, 2) not null default 99.00 check (setup_fee >= 0),
  setup_fee_paid_em timestamptz,
  moeda text not null default 'BRL',
  criado_em timestamptz not null default now()
);

create table if not exists public.faturas (
  id uuid primary key default gen_random_uuid(),
  billing_account_id uuid not null references public.billing_accounts(id) on delete cascade,
  periodo_ano_mes text not null,
  qtd_pedidos integer not null default 0 check (qtd_pedidos >= 0),
  valor_pedidos numeric(10, 2) not null default 0 check (valor_pedidos >= 0),
  valor_setup numeric(10, 2) not null default 0 check (valor_setup >= 0),
  valor_total numeric(10, 2) not null check (valor_total >= 0),
  moeda text not null default 'BRL',
  status text not null default 'aberta'
    check (status in ('aberta', 'enviada', 'paga', 'cancelada')),
  gerada_em timestamptz not null default now(),
  vence_em timestamptz,
  paga_em timestamptz,
  unique (billing_account_id, periodo_ano_mes)
);

create table if not exists public.billing_events (
  id uuid primary key default gen_random_uuid(),
  billing_account_id uuid not null references public.billing_accounts(id) on delete cascade,
  tipo text not null check (tipo in ('setup', 'pedido_confirmado')),
  pedido_id uuid references public.pedidos(id) on delete set null,
  valor numeric(10, 2) not null check (valor >= 0),
  moeda text not null default 'BRL',
  periodo_ano_mes text not null,
  status_cobranca text not null default 'pendente'
    check (status_cobranca in ('pendente', 'faturado', 'pago', 'contestado')),
  fatura_id uuid references public.faturas(id) on delete set null,
  criado_em timestamptz not null default now()
);

create index if not exists unidades_restaurante_id_idx on public.unidades(restaurante_id);
create index if not exists mesas_restaurante_unidade_status_idx on public.mesas(restaurante_id, unidade_id, status);
create index if not exists sessoes_mesa_mesa_status_aberta_idx on public.sessoes_mesa(mesa_id, status, aberta_em desc);
create index if not exists sessoes_mesa_cliente_status_idx on public.sessoes_mesa(cliente_whatsapp, status);
create index if not exists produtos_restaurante_ativo_disponivel_idx on public.produtos(restaurante_id, ativo, disponivel);
create index if not exists produto_aliases_alias_idx on public.produto_aliases(alias);
create index if not exists pedidos_sessao_status_criado_idx on public.pedidos(sessao_mesa_id, status, criado_em desc);
create index if not exists pedidos_mesa_status_criado_idx on public.pedidos(mesa_id, status, criado_em desc);
create index if not exists pedido_itens_pedido_id_idx on public.pedido_itens(pedido_id);
create index if not exists pedido_itens_setor_status_idx on public.pedido_itens(setor, status);
create index if not exists solicitacoes_sessao_status_idx on public.solicitacoes_salao(sessao_mesa_id, status);
create index if not exists solicitacoes_setor_status_criada_idx on public.solicitacoes_salao(setor, status, criada_em desc);
create index if not exists mensagens_remote_jid_criada_idx on public.mensagens_whatsapp(remote_jid, criada_em desc);
create index if not exists mensagens_sessao_criada_idx on public.mensagens_whatsapp(sessao_mesa_id, criada_em desc);
create index if not exists eventos_pedido_pedido_criado_idx on public.eventos_pedido(pedido_id, criado_em desc);
create unique index if not exists billing_events_pedido_unq
  on public.billing_events(pedido_id)
  where pedido_id is not null and tipo = 'pedido_confirmado';
create index if not exists billing_events_account_periodo_idx
  on public.billing_events(billing_account_id, periodo_ano_mes, status_cobranca);
create index if not exists faturas_account_periodo_idx
  on public.faturas(billing_account_id, periodo_ano_mes);

alter table public.restaurantes enable row level security;
alter table public.unidades enable row level security;
alter table public.mesas enable row level security;
alter table public.sessoes_mesa enable row level security;
alter table public.produtos enable row level security;
alter table public.produto_aliases enable row level security;
alter table public.pedidos enable row level security;
alter table public.pedido_itens enable row level security;
alter table public.solicitacoes_salao enable row level security;
alter table public.mensagens_whatsapp enable row level security;
alter table public.eventos_pedido enable row level security;
alter table public.billing_accounts enable row level security;
alter table public.billing_events enable row level security;
alter table public.faturas enable row level security;

