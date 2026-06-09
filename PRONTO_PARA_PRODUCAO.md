# Pronto para Produção — Klink 🚀

> **O que foi feito em 09/06/2026 e o que VOCÊ precisa fazer para ligar de verdade.**
> Resultado do dia: auditoria completa + **17 commits** de correção, testes subindo de
> **367 para 458** (91 testes novos), e **duas rodadas de revisão dupla** (segurança +
> caça-bugs independentes). Veredito das revisões: **seguro para deploy**.

---

## Parte 1 — O que foi corrigido (antes → agora)

### 💰 Cobrança (a parte que protege seu bolso e sua reputação)

| Antes | Agora |
|---|---|
| 4 amigos escaneando o QR da mesma mesa = **4 cobranças** (fatura até 4x maior que o prometido) | Cobrança por **ocupação física da mesa** ("giro"): vários celulares na mesma mesa = **1 cobrança de R$ 3,97** |
| Primeiro amigo que fechava a conta liberava a mesa com os outros ainda pedindo | Mesa só fica livre quando a **última** comanda dela fecha |
| Citar "mesa 8" no meio de uma frase fechava a conta atual em silêncio e cobrava de novo | Troca de mesa só com mensagem explícita ("Mesa 8" sozinho, como o QR manda) |
| A trava dos R$ 147 não travava nada (conta nascia "ativa") | Ao cadastrar o nome real, a conta **espera o setup ser pago** — e o pagamento fica registrado na fatura |
| A primeira fatura cobraria as mesas dos SEUS testes na demo | Mesas da fase demo viram **cortesia** (não entram na fatura) |
| Mesa aberta depois da fatura do mês ficava "pendente" para sempre (dinheiro nunca cobrado) | A próxima fatura **varre** as pendências de meses anteriores |
| Mês da fatura virava às 21h de Brasília (horário de Londres) | Virada à **meia-noite de Brasília** |

### 📱 WhatsApp (o risco de banimento e o restaurante surdo)

| Antes | Agora |
|---|---|
| O bot podia responder a si mesmo em **loop infinito** (= banimento na hora do rush) | Filtro descarta eco do próprio bot, grupos, transmissões, canais e eventos de sistema |
| Número banido → selo "Bot conectado" continuava **verde** e ninguém sabia | Selo com 3 estados honestos + **banner vermelho no painel** + alerta no `/health` para monitor avisar seu celular |
| OpenAI lenta podia **congelar o app inteiro** por até 10 minutos | Tempo limite de 10s (20s para áudio); estourou, o bot cai no atalho por palavra-chave e responde mesmo assim |
| Erro inesperado = cliente no vácuo + mensagem **perdida para sempre** | O bot responde "tive um problema, chama um atendente" e a próxima mensagem funciona normal |
| Mensagem duplicada da Evolution podia virar pedido duplo | Proteção atômica no banco (impossível processar duas vezes) |

### 🍽️ Operação do salão (a vida do dono, do garçom e da cozinha)

| Antes | Agora |
|---|---|
| Pedido só existia numa tela que ninguém era obrigado a olhar | **Comanda chega no WhatsApp da cozinha** (celular velho na parede resolve — e apita sozinho) |
| Preso às 12 mesas da demonstração | **Cadastro de mesas**: "meu salão tem 40 mesas" cria tudo em lote, com QR na hora; renomear e remover |
| Sem botão de fechar mesa (cliente que paga no caixa deixava a mesa "ocupada" por 6h) | Botão **"fechar mesa"** em cada cartão do painel |
| Caixa via "Fechar conta da Mesa 12"… sem valor (somava de cabeça) | Ticket chega com o **total**; o cliente recebe o **extrato itemizado** no WhatsApp; a comanda da equipe traz o valor |
| Cliente que não respondia "1" deixava o pedido morrer (nem o garçom destravava) | Botão **"Enviar pra cozinha ✓"** no rascunho do painel |
| Painel mudo (cozinha tinha que ficar encarando a tela) | **Bip de campainha** quando entra comanda nova |
| Wi-fi caía e o painel congelava mostrando dados velhos sem aviso | Tarja **"SEM CONEXÃO"** aparece (e some sozinha quando a rede volta) |
| "Qual o cardápio?" → "chamei um atendente" (cliente sem preço em lugar nenhum) | O bot **responde o cardápio** com preços, por categoria, em 3 idiomas |
| "Manda 100 picanhas" entrava direto na fila da cozinha | Acima de 30 unidades, o bot **chama um atendente** para confirmar na mesa |

### 🛡️ Infraestrutura (o que salvava ou perdia tudo)

| Antes | Agora |
|---|---|
| Comando de backup do manual **não funcionava** (programa não instalado) | Programa instalado na imagem + manual corrigido e testável |
| Nenhuma cópia fora do servidor (VPS morre = perde tudo) | Rota **`/admin/backup`**: baixa o banco inteiro num comando, de qualquer lugar |
| Comandos de cobrança do manual falhariam em produção (faltava a senha) | Manual corrigido (`-u admin:senha` em todos) |
| Zero monitoramento (você descobria pelo telefonema furioso) | Seção de **monitoramento** no DEPLOY.md: 2 monitores gratuitos avisam seu celular |

---

## Parte 2 — O que VOCÊ precisa fazer (checklist de produção)

### Passo 1 — Subir o código novo
- [ ] `git push` para o GitHub (os 17 commits estão no seu computador).
- [ ] No Coolify, clicar em **Deploy** (ou esperar o deploy automático).
- [ ] **Antes do deploy**: conferir que o volume **`/data`** está montado (Persistent
  Storage) — sem ele o banco morre a cada deploy.

### Passo 2 — Variáveis de ambiente no Coolify (conferir/adicionar)
```
KLINK_DASHBOARD_PASSWORD=<senha forte>          (obrigatória — o app não sobe sem)
KLINK_ADMIN_TOKEN=<token aleatório>             (obrigatório p/ cobrança e backup)
KLINK_WEBHOOK_SECRET=<segredo>                  (obrigatório — protege o webhook)
KLINK_REQUIRE_TABLE_VALIDATION=true             (garçom valida mesa = anti-trote)
KLINK_DATABASE=/data/klink.db
EVOLUTION_API_URL / _KEY / _INSTANCE            (exclusivos deste cliente)
OPENAI_API_KEY
EVOLUTION_DAILY_LIMIT=1000                      (o padrão 200 estoura numa sexta cheia;
                                                 suba GRADUALMENTE — chip novo começa
                                                 com 200 e aquece por 1-2 semanas)
```

### Passo 3 — Webhook da Evolution (mudou!)
- [ ] URL: `https://<cliente>.../webhook/evolution/<KLINK_WEBHOOK_SECRET>`
- [ ] Eventos: **`MESSAGES_UPSERT` e `CONNECTION_UPDATE`** (o segundo é novo — é o
  que torna o selo de conexão honesto e liga o alerta de queda).

### Passo 4 — Configurações no painel (5 minutos)
- [ ] **Configurações** → nome do restaurante + número do bot + **"WhatsApp da
  equipe"** (novo!): crie um grupo "Cozinha" no WhatsApp, com o celular da cozinha
  e os garçons — a comanda cai lá e apita sozinha.
- [ ] ⚠️ Ao salvar o nome real, o bot **trava em "aguardando setup"** (proposital).
  Rode o comando do Passo 6 para destravar.
- [ ] **QR codes** → "Meu salão tem N mesas" → criar → **Imprimir** → colar nas mesas.

### Passo 5 — Backup (30 minutos, UMA vez)
- [ ] Coolify → Scheduled Tasks → criar a tarefa diária (comando pronto no
  `DEPLOY.md`, seção 💾). **Rodar 1x pelo botão e conferir que o arquivo apareceu.**
- [ ] Do seu computador, baixar uma cópia externa:
  `curl .../admin/backup -u admin:<senha> -H "X-Admin-Token: <token>" -o backup.db`
  (agendar 1x/dia no Agendador de Tarefas do Windows).
- [ ] **Testar a restauração UMA vez** (passo a passo no DEPLOY.md). Backup que
  nunca foi restaurado em teste é esperança, não backup.

### Passo 6 — Cobrança (quando o Pix do cliente cair)
```bash
curl -X POST https://<cliente>.../admin/billing/setup-paid \
  -u admin:<KLINK_DASHBOARD_PASSWORD> -H "X-Admin-Token: <KLINK_ADMIN_TOKEN>"
```
- Isso destrava o bot E registra os R$ 147 no histórico (auditável na fatura).

### Passo 7 — Monitoramento (15 minutos, evita o telefonema furioso)
- [ ] Criar conta gratuita no UptimeRobot (uptimerobot.com).
- [ ] Monitor 1 (servidor caiu): HTTP em `https://<cliente>.../health`, 1-5 min.
- [ ] Monitor 2 (WhatsApp caiu): tipo *Keyword*, mesma URL, palavra-chave
  **`whatsapp_desconectado`**, alertar quando a palavra EXISTIR.
- [ ] Colocar seu celular/e-mail como contato de alerta.

### Passo 8 — Teste de fogo (antes da primeira sexta-feira)
- [ ] Mandar "Mesa 1" → validar no painel → pedir → confirmar com "1".
- [ ] Conferir: comanda chegou no grupo da cozinha? Bip tocou no painel?
- [ ] "fecha a conta" → extrato chegou no seu WhatsApp? Total apareceu no caixa?
- [ ] Desconectar a Evolution de propósito → banner vermelho apareceu? Alerta chegou?
- [ ] Combinar com a equipe a regra de ouro: **cliente pagou e saiu = clicar
  "fechar mesa"** (é o que fecha o "giro" e libera a mesa pro próximo grupo).

---

## Parte 3 — O que fica para depois (backlog honesto)

Nada disso impede o piloto; é o caminho de crescimento:

1. **Impressora térmica de comanda** (casas maiores; o grupo de WhatsApp resolve o boteco).
2. **Relatório de vendas para o dono** (quanto vendi hoje/semana/mês — os dados já estão no banco, falta a tela).
3. **Garçom lançar pedido completo pelo painel** (mesa sem WhatsApp; hoje ele já destrava rascunhos).
4. **Modificadores estruturados** (meia porção, combo, ponto da carne com botão — hoje vai como observação de texto).
5. **Taxa de serviço (10%) e couvert** no extrato.
6. **Nota fiscal / integração com PDV** — por enquanto, posicionar como "comanda digital" (o caixa cobra como sempre cobrou).
7. **Lembrete automático** para rascunho não confirmado (precisa de agendador).
8. **LGPD**: política de privacidade na landing + rotina de limpeza de dados antigos.
9. **Horário de funcionamento** (bot não abrir mesa às 3h da manhã).
10. **Migrar para a API oficial da Meta** ao passar de ~10 casas (elimina de vez o risco de banimento).
11. **Multi-tenant real** (Caminho B do ARQUITETURA.md) ao passar de ~20-30 clientes.
12. **Rever o preço**: 30 mesas × 1,5 giro × 25 dias ≈ R$ 4.466/mês — mais caro que um
    garçom CLT. Estude um **teto mensal** (ex.: "no máximo R$ 397/mês") ou planos por faixa.

---

## Números do dia

| Métrica | Valor |
|---|---|
| Falhas graves encontradas na auditoria | 38 (+ 15 extras) |
| Corrigidas hoje | **As 14 mais críticas** (2 levas) + 10 achados das revisões |
| Commits | 17 |
| Testes | 367 → **458** (91 novos, todos passando) |
| Revisões independentes | 4 (2 de segurança, 2 de caça-bugs) |
| Veredito de segurança | ✅ Pode ir para produção (com o checklist acima) |
