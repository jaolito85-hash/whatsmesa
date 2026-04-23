# Deploy no Coolify — MesaZap

Guia passo a passo para subir o MesaZap numa VPS com Coolify usando SQLite em
volume persistente.

## Pre-requisitos

- VPS com Coolify v4 instalado e funcionando (Docker rodando, Traefik ativo).
- Repo publico ja no ar: <https://github.com/jaolito85-hash/whatsmesa>
- Evolution API ja rodando: <http://evo-h8cos48wogk0w804ss08soko.72.60.13.166.sslip.io>
- Numero WhatsApp + API key + nome da instancia (preencher no .env).
- Chave da OpenAI (opcional; sem ela o parser heuristico assume).

Dominio: piloto usa o sslip.io que o Coolify gera automaticamente
(ex.: `mesazap-xxx.72.60.13.166.sslip.io`). Nao precisa configurar DNS.

## 1. Criar a aplicacao no Coolify

1. **Projects → New Project** → nome: `MesaZap`.
2. **New Resource → Application → Public Repository**.
3. **Repository URL**: `https://github.com/jaolito85-hash/whatsmesa`.
4. **Branch**: `main`.
5. **Build Pack**: `Dockerfile`.
6. **Dockerfile Location**: `Dockerfile` (raiz).
7. Salvar. Coolify ja gera um sslip.io automaticamente (anote a URL — sera
   usada como `MESAZAP_PUBLIC_BASE_URL` e como webhook na Evolution).

## 3. Configurar volume persistente para o SQLite

Em **Persistent Storage** da aplicacao:

- **Name**: `mesazap-data`
- **Mount Path**: `/data`
- **Type**: Volume

Isso garante que o arquivo `mesazap.db` sobrevive a rebuilds.

## 4. Porta e dominio

- **Port Exposes**: `5000`
- **Domains**: deixar em branco — Coolify gera automaticamente um sslip.io
  (ex.: `https://mesazap-abc123.72.60.13.166.sslip.io`). Anote essa URL.

Quando migrar para dominio proprio, adicione aqui e Coolify cuida do
Traefik + Lets Encrypt.

## 5. Variaveis de ambiente

Em **Environment Variables** (substitua `<URL_GERADA>` pela URL sslip.io
do passo 4):

```env
MESAZAP_DATABASE=/data/mesazap.db
MESAZAP_PUBLIC_BASE_URL=https://<URL_GERADA>

WHATSAPP_PHONE=
EVOLUTION_API_URL=http://evo-h8cos48wogk0w804ss08soko.72.60.13.166.sslip.io
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe

MESAZAP_DASHBOARD_USER=admin
MESAZAP_DASHBOARD_PASSWORD=GERE-UMA-SENHA-FORTE
MESAZAP_ADMIN_TOKEN=GERE-UM-TOKEN-ALEATORIO-32-CHARS
```

Preencha `WHATSAPP_PHONE`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE` antes
do go-live com os dados reais do piloto.

Dica: para gerar tokens aleatorios, no terminal `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Supabase nao e necessario agora (estamos usando SQLite).

## 6. Healthcheck

O proprio `Dockerfile` ja tem um `HEALTHCHECK` apontando para `/health`.
Coolify usa esse check para decidir quando a aplicacao esta pronta.

## 7. Deploy

Clicar em **Deploy**. Coolify faz:

1. Pull do repositorio.
2. `docker build` usando o `Dockerfile`.
3. Start com volume montado em `/data`.
4. Traefik expoe em HTTPS.

Primeiro deploy leva ~3-5 minutos. Logs aparecem em tempo real.

## 8. Smoke test pos-deploy

```bash
# 1. Healthcheck
curl https://<URL_GERADA>/health
# {"ok": true, "service": "mesazap"}

# 2. Painel (pede login HTTP Basic com user e senha do env)
curl -u "admin:SUA-SENHA" https://<URL_GERADA>/ | head -20

# 3. Billing usage
curl -u "admin:SUA-SENHA" https://<URL_GERADA>/api/billing/usage

# 4. Webhook demo (sem auth, publico para a Evolution API)
curl -X POST https://<URL_GERADA>/webhook/evolution \
  -H "Content-Type: application/json" \
  -d '{"data":{"key":{"id":"teste-1","remoteJid":"5511999999999"},"message":{"conversation":"Mesa 12"}}}'
```

## 9. Conectar Evolution API

Na instancia da Evolution, configure o webhook:

- **URL**: `https://<URL_GERADA>/webhook/evolution`
- **Eventos**: `MESSAGES_UPSERT` (ou similar ao seu setup).

Teste enviando `Mesa 12` de um WhatsApp para o numero conectado. O bot deve
responder `Mesa 12 liberada. Pode pedir por audio ou texto.`

## 10. Cobrar a taxa de setup (R$ 99)

Apos o cliente pagar via Pix, marque como pago:

```bash
curl -X POST https://<URL_GERADA>/admin/billing/setup-paid \
  -H "X-Admin-Token: SEU-ADMIN-TOKEN"
```

A conta sai de `aguardando_setup` para `ativo` e o soft lock libera.

## 11. Fechar fatura mensal

No primeiro dia do mes seguinte:

```bash
curl -X POST https://<URL_GERADA>/admin/billing/generate-invoice \
  -H "X-Admin-Token: SEU-ADMIN-TOKEN"
```

A fatura fica `aberta`. Gere o Pix externamente, cobre, e quando receber:

```bash
curl -X POST https://<URL_GERADA>/admin/billing/invoice/<FATURA_ID>/paid \
  -H "X-Admin-Token: SEU-ADMIN-TOKEN"
```

Usar o id que vier na resposta do `generate-invoice`.

## 12. Backup do SQLite

Uma vez por dia, copiar `/data/mesazap.db` para um bucket ou pasta segura:

```bash
# Dentro da VPS
docker cp mesazap-container:/data/mesazap.db ~/backups/mesazap-$(date +%F).db
```

Ou usar o **Scheduled Tasks** do Coolify para automatizar.

## Problemas comuns

- **401 em todas as rotas privadas**: senha do dashboard nao foi setada ou
  esta diferente. Confira `MESAZAP_DASHBOARD_PASSWORD`.
- **Webhook nao responde**: verifique se a rota `/webhook/evolution` esta
  publica (nao exige auth) no seu deploy. Teste com `curl` direto.
- **Audio nao transcreve**: confira `OPENAI_API_KEY` e o formato enviado.
  Evolution API manda `.ogg` por padrao (suportado nativamente).
- **Conta fica em `aguardando_setup`**: chame `POST /admin/billing/setup-paid`
  com o `X-Admin-Token` correto.
- **SQLite bloqueia em concorrencia**: o Dockerfile ja roda com 1 worker +
  4 threads e WAL mode + busy_timeout. Isso aguenta bem o MVP. Se escalar,
  migre para Postgres via Supabase antes de aumentar workers.

## Quando migrar do SQLite

Indicadores de que ja passou da hora:

- Mais de 50 restaurantes ativos.
- Pedidos por minuto em pico acima de 30.
- Backup ficando caro/lento.
- Precisa de dashboard externo (metabase, etc.) lendo a base.

Nesse ponto, portar `storage.py` para Postgres (via Supabase) e usar o
`supabase/schema.sql` que ja esta no repo.
