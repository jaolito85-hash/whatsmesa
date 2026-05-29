# Progresso — Klink

> Diário de bordo do projeto, em linguagem simples. Atualizado a cada mudança.
> Última atualização: **29/05/2026**

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
| Testes automáticos | 329/329 passando ✅ |
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
- [ ] Cadastrar o primeiro restaurante de verdade (substituir o "Klink Demo" pelo nome real do estabelecimento).
- [ ] Trocar a foto stock do painel pela foto real do estabelecimento.

---

## Histórico — o que foi feito (mais recente primeiro)

### 29/05/2026 — Logos e identidade visual do Klink no site e no painel
- Você criou a marca: o **mascote** (campainha de recepção com rostinho e fone de
  atendente) + a palavra **klink** com o pontinho do "i" em verde.
- Coloquei essas logos no **painel** (onde aparecia "MZ", agora aparece o mascote +
  "klink") e na **landing page** (topo, rodapé e o mascote "espiando" no celular).
- Recortei o fundo do mascote pra ele ficar **transparente** e funcionar em qualquer
  lugar. A palavra "klink" foi refeita de um jeito que **nunca borra** (fica nítida em
  qualquer tamanho, do favicon ao banner) e o pontinho verde fica sempre no lugar.
- Troquei a cor antiga (amarelo-limão, herança do MesaZap) pelo **verde da marca**
  (#49B548) no site e no painel. Mantive um amarelo só para avisos de "aguardando".
- Troquei uma foto genérica de banco de imagens por um **print real do nosso painel**
  na landing. Adicionei o **favicon** (ícone da abinha do navegador) nas duas páginas.
- Corrigi o e-mail de contato para **contato@klinkai.com.br**.
- Conferi tudo abrindo as telas de verdade (screenshots) e rodei os testes: **329 ok**.

### 29/05/2026 — Nome oficial agora é Klink
- Você registrou a marca **`klinkai.com.br`**. Decidimos adotar o nome **Klink** em tudo.
- Trocamos **todas as 175 menções** de "MesaZap" por "Klink" no projeto:
  textos do site/painel, documentação, e também a "pasta do motor" do sistema
  (que se chamava `mesazap` e agora se chama `klink`).
- As "etiquetas técnicas" usadas no servidor também mudaram de nome
  (ex.: `MESAZAP_DATABASE` virou `KLINK_DATABASE`). **Atenção na próxima subida:**
  é preciso atualizar essas etiquetas no Coolify (detalhes ao final desta sessão).
- O nome que o cliente vê é só **Klink** (o `.ai` é só o endereço do site, não o nome).
- Rodamos os testes depois da troca: **329 passaram, nada quebrou.**
- Pastas de vídeo de demonstração antigas (`video-mesazap-*`) foram mantidas como
  estão, por estarem fora do código do produto.

### 29/05/2026 — Mais testes automáticos + correção do carimbo duplo

Usamos o ajudante "test-writer" para cobrir dois pedaços importantes do
sistema que ainda não tinham testes próprios:

1. **Pedidos (`order_service`):** 60 novos testes — transições de status,
   cálculo do total (com cuidado nos centavos) e confirmação de pedido.
2. **Cardápio (`menu_service`):** 72 novos testes — busca de itens por nome
   e apelidos (português, inglês, espanhol), quantidade por extenso,
   itens indisponíveis e desambiguação (ex.: qual "Brahma").

**Correção feita:** ao escrever os testes, descobrimos que confirmar o mesmo
pedido duas vezes gravava **dois carimbos** de "pedido confirmado" no
histórico. Corrigimos para gravar só quando a confirmação realmente acontece.
O status do pedido já estava protegido — era só o histórico que duplicava.

**Resultado:** a suíte saltou de **54 para 186 testes**, todos passando. ✅

### 29/05/2026 — Testes do coração do app + 2 correções e auditoria de segurança

Cobrimos com testes o módulo mais importante e arriscado, o `restaurant_agent`
(o "cérebro" que lê a mensagem do cliente e vira pedido): **135 novos testes**.

Escrevendo esses testes, apareceram dois problemas, ambos corrigidos:

1. **Cobrança duplicada (copia-e-cola):** o trecho que registra a cobrança ao
   abrir a mesa estava escrito **duas vezes seguidas, idêntico**. Apagamos a
   cópia. (Na prática não cobrava em dobro graças a uma trava, mas era
   perigoso.)
2. **Pedido sumia quando faltava um item:** se o cliente pedia dois itens e um
   não existia no cardápio, o app **descartava o pedido inteiro em silêncio**.
   Agora ele **cria o pedido com o que existe e avisa** o que faltou. Se nada
   existe, dá um aviso claro em vez de sumir.

**Auditoria de segurança (security-reviewer):** rodamos uma revisão focada em
cobrança e login do painel. Ela apontou 3 pontos críticos — **todos corrigidos
nesta mesma rodada**:

1. **Cobrança dupla em corrida:** se chegarem duas mensagens iguais ao mesmo
   tempo, podia cobrar 2x. Trocamos por uma trava forte no próprio banco
   (`INSERT OR IGNORE` + índice único): agora só uma cobrança "vence" e a outra
   é ignorada sem erro.
2. **Senha do admin sem proteção:** a comparação do token de admin agora usa
   `hmac.compare_digest` (impede descobrir a senha "medindo o tempo").
3. **Painel aberto se esquecer a senha:** se o token de admin ficar vazio no
   servidor, as rotas de cobrança agora **negam acesso** (antes liberavam). Para
   rodar localmente sem token, basta ligar `KLINK_DEV_MODE=1` (nunca em
   produção).

Também resolvemos os achados médios/baixos da auditoria:

- **Preço padrão do banco desatualizado:** o "valor de fábrica" gravado no banco
  ainda era o antigo (1,97 e setup 99). Alinhamos para o modelo atual (3,97 e
  setup 147), evitando cobrar errado uma conta criada fora do fluxo normal.
- **Centavos com "sobra" de calculadora:** valores de dinheiro eram somados de um
  jeito que podia deixar resto (ex.: 100 mesas davam R$ 396,9999 em vez de
  R$ 397,00). Passamos a somar em centavos exatos.

**Resultado:** a suíte foi de **186 para 329 testes**, todos passando. ✅

### 11/05/2026 — Landing Page e Novo Modelo de Cobrança (Klink)
**Commit:** `landing-page-billing`

Criei uma landing page moderna e atualizei o modelo de negócio:

1. **Nova Landing Page:** Criado `templates/landing.html` com design focado em conversão, usando Tailwind CSS e a identidade visual do projeto (Klink). Inclui o screenshot real do painel Kanban.
2. **Novo Modelo de Cobrança:**
   - **Setup Inicial:** R$ 147,00 (configuração e QR Codes).
   - **Uso:** R$ 3,97 por **mesa aberta** (em vez de por pedido).
3. **Reorganização de Rotas:** 
   - A landing page agora está na raiz (`/`).
   - O painel operacional (dashboard) foi movido para `/dashboard`.
4. **Segurança e Backend:** 
   - Atualizada a lógica de autenticação no `app.py`.
   - Sistema de cobrança migrado para registrar eventos por sessão de mesa.
   - Adicionada migração automática de banco de dados para suportar o novo modelo.
5. **Testes:** Todos os 54 testes unitários e de integração atualizados e passando.

---

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
