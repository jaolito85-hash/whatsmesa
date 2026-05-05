# Progresso — MesaZap (futuro Klink)

> Diário de bordo do projeto, em linguagem simples. Atualizado a cada mudança.
> Última atualização: **05/05/2026**

---

## O que é o app

Um **garçom invisível dentro do WhatsApp** para bares e restaurantes.

O cliente senta na mesa, escaneia um QR Code, manda mensagem ("Mesa 12") no
WhatsApp do estabelecimento e começa a pedir por texto ou áudio. O pedido
cai num painel kanban dividido por setor (Bar, Cozinha, Salão, Caixa) que
o garçom acompanha pelo computador/celular.

**Cobrança do nosso lado:** R$ 99 de setup + **R$ 1,97 por pedido confirmado**.

---

## Status atual

| Item | Situação |
|------|----------|
| Código | Pronto e rodando |
| Repositório | https://github.com/jaolito85-hash/whatsmesa (público) |
| Servidor | Coolify, na sua VPS |
| URL do app | `https://g7yafnc904l4nk0rkfibx6fa.72.60.13.166.sslip.io` |
| WhatsApp (Evolution) | URL configurada, falta API Key + número |
| Testes automáticos | 53/53 passando ✅ |
| Cliente do piloto | Ainda não definido |
| Nome final do produto | A decidir (favorito: **Klink**) |
| Domínio | `klink.bar` comprado por US$ 2,80/ano |

---

## Decisões já tomadas

- **Nome do código no GitHub:** `whatsmesa` (provisório).
- **Nome comercial:** preferência por **Klink** (som universal de copos brindando, funciona em qualquer idioma). Domínio `klink.bar` já reservado.
- **Domínio do piloto:** vamos usar o que o Coolify gera de graça (`sslip.io`). Quando o cliente real entrar, plugamos o `klink.bar` ou subdomínio próprio.
- **Banco de dados:** SQLite (simples, rápido, aguenta o MVP). Migra pra Postgres quando passar de 50 clientes.
- **WhatsApp:** Evolution API (não-oficial, só pra piloto). Cliente grande migra pra WhatsApp Cloud API oficial.

---

## O que falta antes do primeiro cliente pagante

- [ ] Definir nome final (Klink ou outro). Verificar marca registrada no INPI classes 9 (software) e 43 (restaurante).
- [ ] Comprar `klink.app` adicional (~US$ 8) pra travar a marca.
- [ ] Trocar o ícone do WhatsApp na logo (usar literalmente o logo da Meta = risco de processo).
- [ ] Pegar API Key + nome da instância da Evolution e botar no Coolify.
- [ ] Pegar o número de WhatsApp do garçom (chip dedicado de preferência).
- [ ] Cadastrar o primeiro restaurante de verdade (substituir o "MesaZap Demo" pelo nome real do estabelecimento).
- [ ] Trocar a foto stock do painel pela foto real do estabelecimento.

---

## Histórico — o que foi feito (mais recente primeiro)

### 05/05/2026 — Robustez para cliente pagante real
**Commit:** `bc670a1`

Adicionei 4 coisas que protegem o app quando ele virar produção de verdade:

1. **Modo anti-golpe (opcional).** Se ligado, quando alguém escaneia o QR
   e manda "Mesa 12", o bot responde "aguarde o garçom validar". O garçom
   vê uma faixa amarela no topo do painel com botões **validar** / **recusar**.
   Só depois de clicar validar é que o cliente pode pedir. Isso evita pessoa
   de casa pedindo comida fictícia. Por padrão vem desligado pra não
   atrapalhar o piloto inicial.

2. **Tela de saúde do app.** Você abre `/health` no navegador e vê:
   quantas mensagens já saíram hoje, se tá perto do limite, quantas mesas
   ativas, quando chegou a última mensagem. Útil pra colocar num monitor
   externo (UptimeRobot) que avisa por e-mail se algo cair.

3. **Aviso de "WhatsApp quase sendo banido".** Quando passa de 140 mensagens
   por dia (70% do limite informal de 200), o sistema registra um aviso
   no log do Coolify. Você vê e pode reduzir o ritmo.

4. **Mais capacidade.** Antes o app aguentava 4 mensagens em paralelo,
   agora aguenta 8. Suficiente pra bar com 50 mesas em pico.

5. **Backup automático.** Adicionei no manual o passo pra configurar
   cópia diária do banco (4h da manhã), mantendo as últimas 14.

---

### 05/05/2026 — 3 buracos críticos antes do piloto
**Commit:** `05f7b31`

Encontrei 3 problemas que iam aparecer em qualquer cliente real e
consertei antes:

1. **QR Code da mesa agora muda quando a mesa fecha.** Antes, se alguém
   tirasse foto do QR e levasse pra casa, podia continuar pedindo comida
   semanas depois. Agora cada mesa "renova" o QR toda vez que o garçom
   finaliza a conta — a foto antiga deixa de funcionar.

2. **Cliente que troca de mesa não fica com pé em duas.** Antes, se você
   abria sessão na Mesa 12, esquecia, e ia pra Mesa 5, ficava com as duas
   abertas. Agora a antiga fecha automaticamente quando você abre uma nova.

3. **Sessões abandonadas fecham sozinhas em 6 horas.** Cliente saiu sem
   pedir a conta? Depois de 6h sem mandar mensagem, o sistema fecha a
   mesa automaticamente e renova o QR. Sem "mesa fantasma" no painel.

4. **Bônus:** quando o garçom marca "fechar conta" como concluído no
   painel, agora a mesa fecha de verdade. Antes ficava em estado
   intermediário pra sempre.

---

### 05/05/2026 — Avaliação honesta do app
Você me pediu sinceridade sobre o painel. Dei nota **8/10**: design
limpo, KPIs bons, kanban funciona. Pontos a melhorar identificados:
acentos faltando (corrigido logo em seguida), foto stock genérica,
falta indicador de status do WhatsApp na UI (já resolvido com /health),
sem onboarding na tela vazia.

---

### 05/05/2026 — Discussão de naming e logo
- Nome **MesaZap** já existe no Brasil. Decidimos buscar nome global.
- Sugeri 10+ opções (Klink, Trya, Pingo, Mesai, etc.).
- Maioria com `.com` tomado por especuladores de domínio.
- Estratégia: usar TLD do nicho (`.bar`, `.menu`, `.app`).
- **Você comprou `klink.bar`** por US$ 2,80 (1º ano).
- ⚠️ Renovação custa US$ 65/ano — vale transferir pra Cloudflare Registrar
  depois (custa ~US$ 20-30/ano lá).
- Logo: você gostou da mão com bandeja segurando celular. Aprovei o
  conceito, mas alertei que o **ícone do WhatsApp dentro do celular precisa
  ser trocado** — usar o logo oficial é violação de marca da Meta.

---

### 05/05/2026 — Acentos PT-BR
**Commit:** `70d67ca`

O painel mostrava "garcom invisivel", "Salao", "Confirmacao", "Producao"
sem acento — parecia app traduzido por gringo. Corrigi todas as strings
visíveis (painel + mensagens do bot no WhatsApp) com acentuação
correta. 25 testes continuaram passando.

---

### 05/05/2026 — Subiu no Coolify
Deploy do app na sua VPS via Coolify. Configurado:
- Repositório público no GitHub (`whatsmesa`)
- Build via Dockerfile
- Volume persistente em `/data` (banco SQLite sobrevive a redeploys)
- Domínio sslip.io gratuito gerado pelo Coolify
- Variáveis de ambiente: senha do painel, token admin, URL da Evolution
- Status: aplicativo online, painel acessível

---

### 05/05/2026 — Repositório criado
**Commit inicial:** `9cf4b82`

Criado repo público `jaolito85-hash/whatsmesa` no GitHub. Primeiro
commit com todo o código do MVP, Dockerfile, docker-compose, manual
de deploy e 25 testes automatizados.

---

### Antes — desenvolvimento do MVP
O app já tinha sido construído antes desta etapa de operação. Funções
prontas:
- Cardápio multilíngue (PT, EN, ES) com aliases por produto
- Reconhecimento de pedidos por texto e áudio (transcrição via OpenAI)
- Confirmação antes de mandar pra cozinha (cliente confirma com "1")
- Painel kanban Bar/Cozinha/Salão/Caixa em tempo real
- Sistema de cobrança (R$ 99 setup + R$ 1,97/pedido) com faturas mensais
- Auth no painel (usuário/senha)
- Multi-idioma no bot (responde no idioma do cliente)
- Suporte a chamados (chamar garçom, pedir guardanapo, etc.)

---

## Próximos passos sugeridos (depois do piloto)

Ordem de prioridade:

1. **Múltiplos clientes** — hoje cada cliente vai precisar de 1 deploy
   próprio no Coolify. Quando passar de 5-10 clientes, vale criar painel
   admin global pra gerenciar todos.
2. **Cliente cadastra cardápio sozinho** — hoje os produtos são
   plantados em código. Construir tela de admin pro próprio cliente
   subir cardápio.
3. **WhatsApp Cloud API oficial** — quando algum cliente passar de 200
   pedidos/dia, migrar dele pra API oficial da Meta (custa por conversa
   mas não bane o número).
4. **Processar mensagens em paralelo** — quando algum cliente passar de
   30 pedidos/minuto em pico real, mudar o app pra processar mensagens
   numa fila assíncrona (não trava se chegar muita coisa junto).
5. **Migrar de SQLite pra Postgres** — quando tiver 50+ clientes ativos
   ou o backup ficar lento.

---

## Como manter este documento atualizado

Toda vez que você me pedir uma mudança no projeto, vou:
1. Fazer a mudança no código.
2. Rodar os testes.
3. Fazer o commit.
4. **Atualizar este `PROGRESSO.md`** adicionando uma nova entrada no topo
   da seção "Histórico" com a data, número do commit e o que mudou em
   linguagem simples.
5. Atualizar a tabela de **Status atual** se algo nela mudou.

Se eu esquecer, me lembre: *"atualiza o PROGRESSO.md"*.
