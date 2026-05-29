# Deploy no Coolify — Klink

Guia passo a passo para subir o Klink numa VPS com Coolify usando SQLite em
volume persistente.

## Pre-requisitos

- VPS com Coolify v4 instalado e funcionando (Docker rodando, Traefik ativo).
- Repo publico ja no ar: <https://github.com/jaolito85-hash/whatsmesa>
- Evolution API ja rodando: <http://evo-h8cos48wogk0w804ss08soko.72.60.13.166.sslip.io>
- Numero WhatsApp + API key + nome da instancia (preencher no .env).
- Chave da OpenAI (opcional; sem ela o parser heuristico assume).

Dominio: piloto usa o sslip.io que o Coolify gera automaticamente
(ex.: `klink-xxx.72.60.13.166.sslip.io`). Nao precisa configurar DNS.

## 1. Criar a aplicacao no Coolify

1. **Projects → New Project** → nome: `Klink`.
2. **New Resource → Application → Public Repository**.
3. **Repository URL**: `https://github.com/jaolito85-hash/whatsmesa`.
4. **Branch**: `main`.
5. **Build Pack**: `Dockerfile`.
6. **Dockerfile Location**: `Dockerfile` (raiz).
7. Salvar. Coolify ja gera um sslip.io automaticamente (anote a URL — sera
   usada como `KLINK_PUBLIC_BASE_URL` e como webhook na Evolution).

## 3. Configurar volume persistente para o SQLite

Em **Persistent Storage** da aplicacao:

- **Name**: `klink-data`
- **Mount Path**: `/data`
- **Type**: Volume

Isso garante que o arquivo `klink.db` sobrevive a rebuilds.

## 4. Porta e dominio

- **Port Exposes**: `5000`
- **Domains**: deixar em branco — Coolify gera automaticamente um sslip.io
  (ex.: `https://klink-abc123.72.60.13.166.sslip.io`). Anote essa URL.

Quando migrar para dominio proprio, adicione aqui e Coolify cuida do
Traefik + Lets Encrypt.

## 5. Variaveis de ambiente

Em **Environment Variables** (substitua `<URL_GERADA>` pela URL sslip.io
do passo 4):

```env
KLINK_DATABASE=/data/klink.db
KLINK_PUBLIC_BASE_URL=https://<URL_GERADA>

WHATSAPP_PHONE=
EVOLUTION_API_URL=http://evo-h8cos48wogk0w804ss08soko.72.60.13.166.sslip.io
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe

KLINK_DASHBOARD_USER=admin
KLINK_DASHBOARD_PASSWORD=GERE-UMA-SENHA-FORTE
KLINK_ADMIN_TOKEN=GERE-UM-TOKEN-ALEATORIO-32-CHARS
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
# {"ok": true, "service": "klink"}

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

Uma vez por dia, copiar `/data/klink.db` para um bucket ou pasta segura.
Use `sqlite3 .backup` (online, atomico, sem lock longo) em vez de `cp`:

```bash
# Dentro do container (Coolify -> Terminal)
sqlite3 /data/klink.db ".backup '/data/backup-$(date +%F).db'"
```

### Automatizar via Coolify Scheduled Tasks

1. Vai em **Scheduled Tasks** -> **+ Add**.
2. **Name**: `daily-backup`
3. **Frequency**: `0 4 * * *` (todo dia 04:00 UTC)
4. **Command**:

   ```bash
   sqlite3 /data/klink.db ".backup '/data/backup-$(date +%F).db'" \
     && find /data -name 'backup-*.db' -mtime +14 -delete
   ```

   Mantem 14 backups mais recentes, apaga os antigos.

5. Para enviar para fora (recomendado), configure **rclone** ou usa um script
   que faz `curl -T` para R2/S3. Volume `/data` e isolado por container, perde
   tudo se a VPS morrer.

## 13. Health check estendido

```bash
curl https://<URL_GERADA>/health
```

Resposta:

```json
{
  "ok": true,
  "service": "klink",
  "whatsapp": {
    "configured": true,
    "sends_today": 47,
    "daily_limit": 200,
    "usage_pct": 23.5,
    "warning": false
  },
  "sessions": {
    "active": 6,
    "pending_validation": 0
  },
  "last_inbound_at": "2026-05-05T18:42:01+00:00",
  "require_table_validation": false
}
```

Quando `usage_pct >= 70`, `warning` vira `true` — sinal para reduzir volume
ou migrar para WhatsApp Cloud API antes de bater limite informal da
Evolution.

## 14. Validacao humana de mesa (anti-fraude)

Por padrao, o cliente que escaneia o QR cai direto em `sessao_ativa` e ja
pode pedir. Em ambiente de fraude alto (chip novo, cidade grande), ative
validacao visual: o garcom precisa clicar **validar** no painel antes do
bot aceitar pedidos.

```env
KLINK_REQUIRE_TABLE_VALIDATION=true
```

Fluxo:

1. Cliente escaneia QR -> manda `Mesa 12` no WhatsApp.
2. Bot responde *"Aguarde o atendente confirmar visualmente que voce esta
   na mesa para liberar o pedido."*
3. Painel mostra faixa **Mesas aguardando garcom confirmar** com botoes
   **validar** / **recusar**.
4. Garcom valida -> bot envia *"Mesa 12 liberada. Pode pedir por audio ou
   texto."* automaticamente.

## Problemas comuns

- **401 em todas as rotas privadas**: senha do dashboard nao foi setada ou
  esta diferente. Confira `KLINK_DASHBOARD_PASSWORD`.
- **Webhook nao responde**: verifique se a rota `/webhook/evolution` esta
  publica (nao exige auth) no seu deploy. Teste com `curl` direto.
- **Audio nao transcreve**: confira `OPENAI_API_KEY` e o formato enviado.
  Evolution API manda `.ogg` por padrao (suportado nativamente).
- **Conta fica em `aguardando_setup`**: chame `POST /admin/billing/setup-paid`
  com o `X-Admin-Token` correto.
- **SQLite bloqueia em concorrencia**: o Dockerfile ja roda com 1 worker +
  8 threads e WAL mode + busy_timeout. Isso aguenta bem o MVP. Se escalar,
  migre para Postgres via Supabase antes de aumentar workers.
- **Sessoes ficam abertas para sempre**: TTL padrao e 6h ocioso. Ajuste
  com `KLINK_SESSION_IDLE_TTL_HOURS=4` (ou outro valor).
- **Limite Evolution proximo**: monitore `usage_pct` em `/health`. Acima de
  70%, log de warning aparece e voce deve reduzir volume ou migrar para
  WhatsApp Cloud API.

## Quando migrar do SQLite

Indicadores de que ja passou da hora:

- Mais de 50 restaurantes ativos.
- Pedidos por minuto em pico acima de 30.
- Backup ficando caro/lento.
- Precisa de dashboard externo (metabase, etc.) lendo a base.

Nesse ponto, portar `storage.py` para Postgres (via Supabase) e usar o
`supabase/schema.sql` que ja esta no repo.
