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
| **A-1** | App sobe sem senha de painel = painel aberto | Aviso forte no boot quando falta `KLINK_DASHBOARD_PASSWORD` (e não é dev). *(Trava de boot completa exige refatorar testes de auth — ver pendências.)* |

Cobertos por **8 testes novos** (`tests/test_webhook_security.py`). Suíte: 351 passando.

### Confirmado OK na auditoria
- **Nenhum segredo no front** (`static/`, `templates/`): o `app.js` só chama `/api/` same-origin.
- **Cobrança sem duplicação**: `record_session_billing` é idempotente (INSERT OR IGNORE + índice único por sessão); `mark_setup_paid` checa `setup_fee_paid_em`.
- **SQL parametrizado** em todo o `storage.py` (sem injeção).

---

## 🔧 Pendências priorizadas (próxima rodada)

**Antes do 2º cliente / primeira fatura real:**
- **A-1 (trava dura):** impedir o app de subir sem senha em produção (hoje é só aviso). Requer ajustar os testes de auth que usam senha vazia.
- **M-3:** `reject_session` aceita rejeitar sessão **já ativa** (que pode ter gerado cobrança) → cobrança órfã. Decidir: ou bloquear (só rejeitar pendente) ou estornar o evento.
- **A-4 / M-2:** tornar `generate_invoice` e `mark_invoice_paid` idempotentes (evitar erro 500 / re-update em chamadas repetidas).
- **B-3 (SSRF):** validar o domínio de `audio_url` antes de baixar (hoje mitigado pelo webhook protegido, mas vale a barreira extra).

**Boa prática / LGPD (quando escalar):**
- **M-4 / A-3:** números de WhatsApp e payloads brutos ficam em texto no banco (`mensagens_whatsapp.payload_bruto`, `cliente_whatsapp`). Definir retenção (ex.: 90 dias) e limpeza.
- **M-1:** `/health` é público e expõe métricas operacionais. Aceitável no piloto; restringir por IP/token ao escalar.
- **B-2:** avisar/abortar se `KLINK_DEV_MODE` estiver ligado em produção.

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
