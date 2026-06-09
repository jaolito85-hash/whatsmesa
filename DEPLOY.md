# Deploy no Coolify — Klink 🛎️

Guia passo a passo para subir **um restaurante** no Coolify (modelo **Caminho A**:
uma instalação por restaurante — ver `ARQUITETURA.md`). SQLite em volume persistente.

> Cada cliente = 1 deploy + 1 subdomínio + 1 senha + 1 número de WhatsApp/instância
> Evolution. Repita este guia para cada novo restaurante.

---

## Pré-requisitos
- VPS com **Coolify** funcionando (Docker + Traefik).
- Repo: <https://github.com/jaolito85-hash/whatsmesa> (branch `main`).
- **Evolution API** rodando + número WhatsApp + API key + nome da instância **deste cliente**.
- **Chave da OpenAI** (recomendada — sem ela o áudio não transcreve).
- **Domínio:** ideal um subdomínio (`<cliente>.klinkai.com.br`) com wildcard
  `*.klinkai.com.br` apontando pro servidor. Se o DNS ainda não estiver pronto, pode
  começar com o `sslip.io` que o Coolify gera automaticamente.

---

## Passo 1 — Criar a aplicação
1. **Projects → New Project** → nome do cliente (ex: `Boteco do Zé`).
2. **New Resource → Application → Public Repository**.
3. **Repository URL:** `https://github.com/jaolito85-hash/whatsmesa` · **Branch:** `main`.
4. **Build Pack:** `Dockerfile` (na raiz).
5. Salvar.

## Passo 2 — Volume persistente (o banco mora aqui)
Em **Persistent Storage → + Add**:
- **Name:** `klink-data` · **Mount Path:** `/data` · **Type:** Volume

⚠️ Sem isso, os dados do restaurante somem a cada deploy.

## Passo 3 — Porta e domínio
- **Port Exposes:** `5000`
- **Domains:** `https://<cliente>.klinkai.com.br` (ou deixe em branco para usar o
  sslip.io gerado). **Anote essa URL** — vira o `KLINK_PUBLIC_BASE_URL`.

## Passo 4 — Variáveis de ambiente
Em **Environment Variables**. Gere segredos fortes com:
`python -c "import secrets; print(secrets.token_urlsafe(32))"`

```env
# Endereço e banco
KLINK_PUBLIC_BASE_URL=https://<cliente>.klinkai.com.br
KLINK_DATABASE=/data/klink.db
KLINK_REQUIRE_TABLE_VALIDATION=true

# Segurança (NUNCA deixe a senha vazia — o app se recusa a subir sem ela)
KLINK_DASHBOARD_USER=admin
KLINK_DASHBOARD_PASSWORD=<senha-forte>
KLINK_ADMIN_TOKEN=<token-aleatorio>
KLINK_WEBHOOK_SECRET=<segredo-do-webhook>

# WhatsApp (Evolution) — exclusivos deste cliente
EVOLUTION_API_URL=http://evo-h8cos48wogk0w804ss08soko.72.60.13.166.sslip.io
EVOLUTION_API_KEY=<chave>
EVOLUTION_INSTANCE=<instancia-deste-cliente>
WHATSAPP_PHONE=<numero-do-bot>

# IA / áudio
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

> **NÃO** ligue `KLINK_DEV_MODE` em produção (abre as rotas de cobrança sem token).

## Passo 5 — Deploy
Clique em **Deploy**. Primeiro build leva ~3–5 min (logs em tempo real). A migração
automática deixa nome/preço corretos sozinha.

## Passo 6 — Conectar a Evolution (webhook COM o segredo)
Na instância da Evolution, configure o webhook **incluindo o segredo no final da URL**:
- **URL:** `https://<cliente>.klinkai.com.br/webhook/evolution/<KLINK_WEBHOOK_SECRET>`
- **Eventos:** `MESSAGES_UPSERT` **e** `CONNECTION_UPDATE`.

Sem o segredo certo na URL, o webhook é **rejeitado** (proteção contra pedidos forjados).

> O `CONNECTION_UPDATE` é o que deixa o selo "Bot conectado" do painel **honesto**:
> se o número cair (banimento, QR expirado), o painel mostra um banner vermelho e o
> `/health` passa a listar `whatsapp_desconectado` em `alerts`. Sem esse evento, o
> selo mostra "estado real desconhecido".

## Passo 7 — Smoke test
```bash
# 1. Saúde (público)
curl https://<cliente>.klinkai.com.br/health
# {"ok": true, "service": "klink", ...}

# 2. Painel (pede a senha)
curl -u "admin:<senha>" https://<cliente>.klinkai.com.br/dashboard | head -5

# 3. Webhook SEM segredo -> deve dar 403 (prova que está protegido)
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<cliente>.klinkai.com.br/webhook/evolution

# 4. Webhook COM segredo -> deve aceitar (200)
curl -X POST https://<cliente>.klinkai.com.br/webhook/evolution/<KLINK_WEBHOOK_SECRET> \
  -H "Content-Type: application/json" \
  -d '{"data":{"key":{"id":"t1","remoteJid":"5511999999999@s.whatsapp.net"},"message":{"conversation":"oi"}}}'
```

## Passo 8 — Cadastrar o restaurante e imprimir os QRs
1. Acesse `https://<cliente>.klinkai.com.br/dashboard` (login: admin + senha).
2. **Configurações** → nome do restaurante + número do WhatsApp + **WhatsApp da
   equipe** (celular da cozinha ou grupo) → **Salvar**.
3. **QR codes** → "Meu salão tem N mesas" → **Imprimir** → recorte e cole nas mesas.

> ⚠️ **Trava do setup:** ao salvar o nome real (sair do modo demo), a conta volta
> para *aguardando setup* e o bot responde "Estamos ajustando algo aqui" até você
> rodar o `setup-paid` do Passo 9. É proposital: cliente real só usa depois que os
> R$ 147 caírem. Por isso, **faça o Passo 9 antes do teste do item 4.**

4. Teste: mande `Mesa 1` do WhatsApp para o número do bot; valide a mesa no painel.

## Passo 9 — Cobrança (setup R$ 147 + fatura mensal)
> ⚠️ As rotas `/admin/*` ficam atrás de DUAS travas: a senha do painel (Basic Auth,
> `-u admin:<senha>`) **e** o token de admin (`X-Admin-Token`). Sem o `-u`, o
> servidor responde 401 mesmo com o token certo.
```bash
# Liberar a conta após o cliente pagar o setup (R$ 147)
curl -X POST https://<cliente>.klinkai.com.br/admin/billing/setup-paid \
  -u admin:<KLINK_DASHBOARD_PASSWORD> \
  -H "X-Admin-Token: <KLINK_ADMIN_TOKEN>"

# No 1º dia do mês seguinte: gerar a fatura (mesas abertas x R$ 3,97)
curl -X POST https://<cliente>.klinkai.com.br/admin/billing/generate-invoice \
  -u admin:<KLINK_DASHBOARD_PASSWORD> \
  -H "X-Admin-Token: <KLINK_ADMIN_TOKEN>"

# Após receber o Pix, marcar a fatura como paga (use o id retornado acima)
curl -X POST https://<cliente>.klinkai.com.br/admin/billing/invoice/<FATURA_ID>/paid \
  -u admin:<KLINK_DASHBOARD_PASSWORD> \
  -H "X-Admin-Token: <KLINK_ADMIN_TOKEN>"
```

---

## ✅ Checklist de segurança (antes do go-live)
- [ ] `KLINK_DASHBOARD_PASSWORD` forte e única deste cliente
- [ ] `KLINK_ADMIN_TOKEN` forte e único
- [ ] `KLINK_WEBHOOK_SECRET` definido **e** na URL do webhook na Evolution
- [ ] `KLINK_REQUIRE_TABLE_VALIDATION=true`
- [ ] `KLINK_DEV_MODE` ausente
- [ ] Volume `/data` montado · HTTPS ativo
- [ ] Smoke test passou (webhook sem segredo = 403)

## 💾 Backup do banco

### 1. Backup diário dentro da VPS (Coolify → Scheduled Tasks)
- **Frequency:** `0 4 * * *` (todo dia 04:00 UTC = 01:00 de Brasília)
- **Command:**
  ```bash
  sqlite3 /data/klink.db ".backup '/data/backup-$(date +%F).db'" \
    && find /data -name 'backup-*.db' -mtime +14 -delete
  ```
- ✅ O programa `sqlite3` já vem instalado na imagem (Dockerfile). Depois de criar a
  tarefa, **rode-a uma vez pelo botão do Coolify e confira na aba de execuções que o
  arquivo `backup-<data>.db` apareceu** — tarefa agendada sem teste é tarefa quebrada.

### 2. Cópia FORA da VPS (obrigatório antes do go-live)
O backup acima morre junto com a VPS. Para ter uma cópia fora, use a rota de download
(atrás da senha do painel + token de admin):
```bash
# Baixa o banco inteiro, pronto para restaurar (rode do SEU computador):
curl -fsS https://<cliente>.klinkai.com.br/admin/backup \
  -u admin:<KLINK_DASHBOARD_PASSWORD> \
  -H "X-Admin-Token: <KLINK_ADMIN_TOKEN>" \
  -o klink-backup-$(date +%F).db
```
- Agende no seu computador (Agendador de Tarefas do Windows) ou num serviço grátis
  (GitHub Actions com cron) — 1x por dia é suficiente no começo.
- Alternativa robusta ao escalar: `rclone` na VPS enviando `/data/backup-*.db` para
  Cloudflare R2 ou Backblaze B2 (custam centavos por mês).

### 3. Teste de restauração (faça UMA vez antes do primeiro cliente)
```bash
# Restaurar = colocar o arquivo no lugar do banco e reiniciar o app:
# 1. Pare o app no Coolify
# 2. Copie o backup para /data/klink.db (substituindo o atual)
# 3. Inicie o app e confira o painel (cardápio, mesas e faturas no lugar)
```
> Backup que nunca foi restaurado em teste não é backup — é esperança.

## 📟 Monitoramento (saiba ANTES do dono ligar furioso)
O pior cenário é o WhatsApp cair às 21h de sexta e ninguém saber. Configure um monitor
gratuito (UptimeRobot, Better Stack etc.) por cliente — leva 5 minutos:

1. **Monitor de uptime:** tipo HTTP(s), URL `https://<cliente>.klinkai.com.br/health`,
   intervalo de 1–5 min. Cai o servidor → alerta no seu celular/e-mail.
2. **Monitor de WhatsApp caído:** tipo "Keyword", mesma URL, palavra-chave
   **`whatsapp_desconectado`**, alertar **quando a palavra EXISTIR**. O `/health`
   só inclui essa palavra em `alerts` quando a Evolution reportou queda da conexão.
3. (Opcional) Palavra-chave `limite_diario_de_envios_alto` — avisa quando os envios
   do dia passarem de 70% do limite (`EVOLUTION_DAILY_LIMIT`).

## Problemas comuns
- **App não sobe / erro no log sobre senha:** falta `KLINK_DASHBOARD_PASSWORD`. Configure.
- **401 em tudo:** senha do painel errada/ausente. Confira `KLINK_DASHBOARD_PASSWORD`.
- **Webhook responde 403:** o segredo na URL não bate com `KLINK_WEBHOOK_SECRET`.
- **Áudio não transcreve:** confira `OPENAI_API_KEY`.
- **Conta travada em `aguardando_setup`:** rode `POST /admin/billing/setup-paid`.
- **`usage_pct` alto no /health (>70%):** volume perto do limite informal da Evolution —
  considere migrar para a WhatsApp Cloud API oficial (ver `SEGURANCA.md`).

## Referências
- **Arquitetura e multi-cliente:** `ARQUITETURA.md`
- **Segurança (auditoria + checklist):** `SEGURANCA.md`
