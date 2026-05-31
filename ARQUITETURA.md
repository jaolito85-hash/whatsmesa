# Arquitetura & Produção — Klink 🛎️

> Como o Klink atende vários restaurantes hoje (Caminho A) e o plano para o
> multi-tenant real (Caminho B). Referência de produção.
> Última atualização: **31/05/2026**

---

## 0. Estado atual (auditado em 31/05/2026)

- **Modelo:** **1 restaurante por instalação.** O código usa "o primeiro restaurante
  ativo" do banco. Não há login por restaurante nem tabela de usuários.
- **Autenticação do painel:** HTTP Basic Auth — **um usuário e uma senha** por
  instalação (`KLINK_DASHBOARD_USER` / `KLINK_DASHBOARD_PASSWORD`).
- **Segredos:** todos no servidor (variáveis de ambiente). ✅ **Nada de chave/senha no
  front** — o `app.js` só chama `/api/...` na mesma origem; as rotas de cobrança
  `/admin/...` exigem `X-Admin-Token` e são acionadas por você, fora do navegador.
- **Cobrança:** já é por restaurante (`restaurante_id`).

**Conclusão:** o sistema está pronto para o **Caminho A** sem nenhuma mudança de código.

---

## 1. Domínios e DNS

| Domínio | Serve | Deploy |
|---|---|---|
| `klinkai.com.br` + `www` | Site / landing (vendas) | Deploy "institucional" |
| `app.klinkai.com.br` | Painel do 1º cliente (ou painel-modelo) | Deploy do cliente |
| `<cliente>.klinkai.com.br` | Painel de cada restaurante | 1 deploy por cliente |

**Para escalar sem criar DNS na mão:** aponte um **wildcard** `*.klinkai.com.br` para o
IP do servidor (registro `A`). Aí cada deploy no Coolify só "reivindica" seu subdomínio
em **Domains**.

> A landing (`/`) e o painel (`/dashboard`) hoje vivem no mesmo app. No domínio
> institucional, o `/dashboard` fica protegido pela senha do painel — então mesmo que
> alguém acesse, não entra. Para 100% de separação no futuro, dá para ter um deploy só
> com a landing.

---

## 2. CAMINHO A — Subir um novo restaurante (passo a passo)

Cada restaurante = **1 deploy + 1 subdomínio + 1 senha + 1 número de WhatsApp**.
Isolamento físico total: bancos separados, impossível um ver o outro.

### Passo a passo
1. **Novo deploy no Coolify** a partir do repositório (Dockerfile). Pode duplicar um
   deploy existente para ir mais rápido.
2. **Domínio:** em *Domains*, coloque `https://<cliente>.klinkai.com.br`.
3. **Persistent Storage:** monte um volume em **`/data`** (é onde o banco
   `klink.db` vive — sem isso, os dados somem a cada deploy).
4. **Variáveis de ambiente** (cada cliente tem as suas):
   ```
   KLINK_PUBLIC_BASE_URL=https://<cliente>.klinkai.com.br
   KLINK_DATABASE=/data/klink.db
   KLINK_REQUIRE_TABLE_VALIDATION=true
   KLINK_DASHBOARD_USER=admin
   KLINK_DASHBOARD_PASSWORD=<senha-forte-única-do-cliente>
   KLINK_ADMIN_TOKEN=<token-aleatório>
   EVOLUTION_API_URL=<url-da-evolution>
   EVOLUTION_API_KEY=<chave>
   EVOLUTION_INSTANCE=<instância-deste-cliente>
   WHATSAPP_PHONE=<número-do-bot-deste-cliente>
   OPENAI_API_KEY=<chave-openai>
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
   ```
5. **Webhook da Evolution** deste cliente → `https://<cliente>.klinkai.com.br/webhook`.
6. **Deploy** e aguarde subir (a correção automática deixa nome/preço certos).
7. No painel do cliente, abra **Configurações** → cadastre o **nome do restaurante** e o
   **WhatsApp** → salvar.
8. Abra **QR codes** → **Imprimir** → recorte e cole nas mesas.

### ⚠️ Regra de ouro
Cada restaurante precisa do **seu próprio número de WhatsApp + sua própria instância
Evolution**. Um número não pode atender dois bares (os pedidos se misturariam).

### Checklist por cliente
- [ ] Subdomínio configurado e com HTTPS
- [ ] Volume `/data` montado
- [ ] Senha do painel forte e **única** deste cliente
- [ ] `DEV_MODE` desligado · validação do garçom ligada
- [ ] Número + instância Evolution exclusivos
- [ ] Webhook apontado pro subdomínio
- [ ] Nome cadastrado nas Configurações
- [ ] QRs impressos e colados

---

## 3. Segurança em produção

**O que já está protegido (auditado):**
- ✅ Nenhum segredo no front.
- ✅ Painel atrás de senha (Basic Auth) quando `KLINK_DASHBOARD_PASSWORD` está definida.
- ✅ Rotas de cobrança `/admin/*` exigem `X-Admin-Token`; bloqueadas se faltar token
  (a menos que `DEV_MODE` esteja ligado — por isso **DEV_MODE off em produção**).
- ✅ QR público (`/qr/...`) só redireciona pro WhatsApp; abertura de mesa depende da
  validação do garçom.

**Itens a confirmar/auditar antes de ligar pra valer:**
- [ ] `KLINK_DASHBOARD_PASSWORD` definida em TODA instalação (vazia = painel aberto!).
- [ ] `KLINK_ADMIN_TOKEN` forte e único por instalação.
- [ ] Proteção do `/webhook` (hoje é público, como a Evolution exige) — avaliar um
  segredo/validação de origem para evitar mensagens forjadas. → rodar o revisor de
  segurança (`/security-review`) antes do go-live.
- [ ] Rate limiting / limite diário da Evolution configurado.

---

## 4. CAMINHO B — Multi-tenant real (plano futuro)

**Quando migrar:** quando criar deploy manual por cliente começar a doer — estimativa
**~20–30 restaurantes**. Antes disso, o Caminho A é mais simples e mais seguro.

**O que precisa ser construído (resumo honesto do tamanho):**
1. **Contas e login por restaurante:** tabela de usuários, senha com hash (bcrypt/argon2),
   sessões (cookie assinado ou JWT). Substitui o Basic Auth único. → é a "tela com admin
   e senha de cada restaurante".
2. **Identificação do tenant:** por **subdomínio** (`barX.klinkai.com.br` → restaurante X)
   ou pelo login. Toda requisição precisa saber "de qual restaurante é".
3. **Isolamento de dados (o ponto MAIS crítico):** hoje várias consultas pegam "o
   primeiro restaurante". No multi-tenant, **toda** consulta tem que filtrar pelo
   `restaurante_id` do tenant logado. Um único esquecimento = dados de um bar vazando no
   painel de outro. Exige revisão linha a linha + testes de isolamento.
4. **Roteamento de WhatsApp:** o webhook chega num número; o sistema precisa mapear
   número/instância → restaurante. Cada restaurante segue precisando do seu número.
5. **Onboarding self-service:** tela de cadastro para o próprio dono criar a conta,
   escolher plano, pagar o setup.

**Riscos:** o item 3 (isolamento) é onde 99% dos bugs de multi-tenant moram. Tem que ser
feito com calma, com testes automatizados que provem que o restaurante A nunca enxerga o
B. **Não dá para apressar perto da Copa.**

**Migração sugerida (incremental, sem big-bang):**
- Fase 1: tabela de usuários + login (mantendo 1 restaurante por instância).
- Fase 2: identificar tenant por subdomínio e filtrar TODAS as queries por `restaurante_id`
  (com testes de isolamento).
- Fase 3: cadastro/onboarding self-service + billing self-service.
- Cada fase com bateria de testes antes de ir pra produção.

---

## TL;DR
- **Agora:** Caminho A — 1 deploy/subdomínio/senha/número por restaurante. Já está pronto.
- **Depois (~20–30 clientes):** Caminho B — multi-tenant com login, isolando tudo por
  `restaurante_id`, feito por fases e com testes de isolamento.
- **Antes do go-live:** rodar `/security-review` e garantir o checklist da seção 3.
