# Segurança — Auditoria & Status (Klink)

> Registro da auditoria de segurança pré-produção e o que foi corrigido.
> Auditoria: **31/05/2026**. Modelo: single-tenant por instância (Caminho A).

---

## ✅ Corrigido em 31/05/2026

| # | Achado | Correção |
|---|--------|----------|
| **C-3** | `/webhook` sem validação de origem → qualquer um podia forjar pedidos e gerar cobrança falsa | Segredo de webhook (`KLINK_WEBHOOK_SECRET`). Se configurado, o `/webhook` só aceita com o segredo no path (`/webhook/evolution/<segredo>`), na query (`?token=`) ou no header `X-Webhook-Token`. |
| **C-2** | `/api/demo/message` público com efeitos reais (abrir mesa, cobrar) | Bloqueado fora de `KLINK_DEV_MODE` (retorna 403 em produção). |
| **C-1** | `debug=True` no `app.run` (risco de RCE se rodado direto) | Trocado para `debug=False`. |
| **A-1** | App sobe sem senha de painel = painel aberto | **Trava de boot em produção**: sem `KLINK_DASHBOARD_PASSWORD` e fora de dev, o app se recusa a subir (sob testes, só avisa). |
| **M-3** | `reject_session` rejeitava sessão já ativa → cobrança órfã | Reject só vale para sessão **pendente**. Encerrar ativa é via `close_session`. |
| **A-4** | `generate_invoice` quebrava (500) em chamada concorrente | Idempotente: trata corrida e retorna a fatura existente. |
| **M-2** | `mark_invoice_paid` re-carimbava fatura já paga | Idempotente: se já paga, retorna sem alterar. |
| **B-3** | `audio_url` baixada sem validação (SSRF p/ rede interna) | `_ensure_public_url` bloqueia loopback/privado/link-local/metadata. |
| **B-2** | `KLINK_DEV_MODE` ligado em produção passava silencioso | Aviso forte no boot quando dev-mode está ativo. |

Cobertos por **18 testes novos** (`tests/test_webhook_security.py`, `tests/test_seguranca_extra.py`). Suíte: **361 passando**.

### Confirmado OK na auditoria
- **Nenhum segredo no front** (`static/`, `templates/`): o `app.js` só chama `/api/` same-origin.
- **Cobrança sem duplicação**: `record_session_billing` é idempotente (INSERT OR IGNORE + índice único por sessão); `mark_setup_paid` checa `setup_fee_paid_em`.
- **SQL parametrizado** em todo o `storage.py` (sem injeção).

---

## 🔧 Pendências restantes (boa prática / quando escalar)

Nada que bloqueie os primeiros clientes — itens de maturidade para quando houver volume:
- **M-4 / A-3 (LGPD):** números de WhatsApp e payloads brutos ficam em texto no banco
  (`mensagens_whatsapp.payload_bruto`, `cliente_whatsapp`). Definir retenção (ex.: 90
  dias) e rotina de limpeza/anonimização.
- **M-1:** `/health` é público e expõe métricas operacionais. Aceitável no piloto;
  restringir por IP/token ao escalar.

---

## 🟢 Recomendações de produção (checklist rápido)
- [ ] `KLINK_DASHBOARD_PASSWORD` forte em toda instalação
- [ ] `KLINK_ADMIN_TOKEN` forte e único
- [ ] `KLINK_WEBHOOK_SECRET` definido **e** configurado na URL do webhook na Evolution
- [ ] `KLINK_REQUIRE_TABLE_VALIDATION=true`
- [ ] `KLINK_DEV_MODE` ausente/false
- [ ] HTTPS (Coolify) + volume `/data` persistente

---

## 📡 WhatsApp: Evolution API vs Cloud API oficial

**Hoje usamos a Evolution API** (não-oficial, baseada no WhatsApp Web). Boa para começar
barato e rápido, mas tem dois riscos reais:
1. **Banimento do número** — é não-oficial e viola os termos do WhatsApp. Em volume alto
   (ex.: Copa), o número pode ser bloqueado no meio do movimento.
2. **Webhook sem assinatura nativa** — por isso adicionamos o `KLINK_WEBHOOK_SECRET`.

**WhatsApp Cloud API (oficial da Meta)** — caminho profissional:
- ✅ Não bane (é oficial), mais estável, **assinatura de webhook nativa** (X-Hub-Signature).
- ✅ Tier inicial gratuito de conversas.
- ⚠️ Setup mais burocrático (Business Manager, número verificado, app aprovado).

**Recomendação:**
- **Piloto agora:** seguir com a Evolution **com o webhook já blindado** + número que não
  seja crítico. Aceitável para os primeiros bares.
- **Antes de escalar (vários bares / volume de Copa):** migrar para a **Cloud API
  oficial** — é o que dá estabilidade e tira o risco de banimento. Já estava no radar.
