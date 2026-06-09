# Auditoria de Operação — Klink 🔍

> Análise feita em **09/06/2026** pensando como **dono de restaurante/bar**: o que
> derruba a operação numa sexta-feira cheia, o que quebra em produção, como funciona
> a história dos números de WhatsApp e das mesas, e como vender sem tablet na cozinha.
>
> Como foi feita: 44 agentes de análise leram o código inteiro. Cada falha grave
> encontrada passou por um **segundo agente cético** que tentou provar que ela era
> falsa lendo o código de novo. Resultado: **38 falhas graves confirmadas, nenhuma
> refutada**, mais 15 pontos que ninguém tinha visto.

---

## Nota geral

O miolo do produto **funciona**: o fluxo de pedido (QR → WhatsApp → painel) está
implementado, a cobrança não duplica, o banco está bem configurado para o porte e há
367 testes passando. O problema não é o que o código faz — é **o que ele NÃO faz
quando algo dá errado** e **duas escolhas de desenho que vão gerar briga com o
cliente** (cobrança por celular e pedido que só existe numa tela).

---

## 1. Os 8 problemas que derrubam a operação (em ordem de perigo)

### 🥇 1. O WhatsApp cai e NINGUÉM fica sabendo — nem você, nem o dono
O selo verde "Bot conectado" na tela de Configurações **mente**: ele só verifica se
as variáveis de configuração estão preenchidas, não se o número está vivo. Se o
número for banido ou a Evolution desconectar às 21h de sexta, os clientes escaneiam
o QR, mandam "Mesa 12"… e silêncio. O painel continua verde. O dono descobre quando
5 mesas reclamam ao mesmo tempo — e volta pro bloquinho pra sempre.
- **Onde:** `config.py:53-55`, `config.html:278-283`, webhook só trata mensagens (nenhum tratamento de evento de conexão no código).
- **Conserto:** tratar o evento de conexão da Evolution, mostrar o estado REAL no painel, e um vigia: "tem mesa aberta e nenhuma mensagem chega há X minutos → banner vermelho + aviso no seu celular".

### 🥈 2. O bot pode responder a si mesmo e entrar em loop infinito (= banimento)
O código não filtra mensagens enviadas pelo próprio bot (`fromMe`). Dependendo da
configuração da Evolution, a resposta do bot volta pelo webhook como se fosse o
cliente falando, o bot responde de novo, e em 2 minutos o número dispara dezenas de
mensagens sozinho — exatamente o comportamento que o WhatsApp pune com banimento.
- **Onde:** `whatsapp_adapter.py:29-65` (nenhuma ocorrência de `fromMe` no projeto inteiro).
- **Conserto:** **5 linhas de código.** Se `fromMe` for verdadeiro, descartar. É a correção mais urgente e mais barata do projeto.

### 🥉 3. Cobrança é por CELULAR, não por mesa — a fatura pode vir 2x a 4x maior que o prometido
Você vende "R$ 3,97 por mesa aberta". O código cobra **R$ 3,97 por telefone que abre
sessão**. Mesa com 4 amigos, cada um escaneia o QR pra pedir sua cerveja: o dono paga
R$ 15,88 por UMA mesa. No fim do mês: "80 mesas?! Meu salão só tem 30!" — sensação de
ser enganado, cancelamento, propaganda negativa. De brinde: os pedidos dos 4 ficam em
4 contas separadas e o caixa precisa juntar tudo na mão.
- **Onde:** `table_session_service.py:97-151` (sessão por telefone+mesa, cobrança na abertura de cada sessão).
- **Conserto:** se a mesa já tem sessão ativa, novos celulares entram na MESMA comanda sem nova cobrança. Cobrar 1x por "giro" da mesa (abriu → fechou).

### 4. Pedido confirmado só existe numa tela que ninguém é obrigado a olhar
Quando o cliente confirma, o pedido vira uma linha no banco e aparece no painel (que
atualiza sozinho a cada 4 segundos) — mas **sem som, sem aviso, sem WhatsApp para a
equipe, sem impressora**. Tela apagada ou aba fechada = a picanha nunca sai. E o bot
ainda diz ao cliente "já mandei para a cozinha", uma promessa que ninguém garantiu.
- **Conserto:** é também a resposta da venda sem tablet — ver seção 6.

### 5. Não existe cadastro de mesas — o restaurante fica preso às 12 mesas da demonstração
Não tem botão para criar a mesa 13, apagar mesa, nem renomear ("Varanda 3"). Um
restaurante de 40 mesas literalmente **não cabe** no produto sem mexer no banco de
dados na mão. É pré-requisito de qualquer venda real.
- **Conserto:** tela de gestão de mesas (criar em lote "1 a 40", renomear, desativar) com QR na hora.

### 6. Backup: o comando documentado NÃO funciona, e não existe cópia fora do servidor
O manual de deploy ensina um backup que usa um programa (`sqlite3`) que **não está
instalado dentro do container** — a tarefa falharia todo dia em silêncio. E mesmo se
funcionasse, o backup ficaria na mesma VPS: se ela morrer, o restaurante perde
cardápio, comandas abertas, histórico e a sua cobrança do mês. Tudo. Irrecuperável.
- **Conserto:** 1 linha no Dockerfile (instalar `sqlite3`) ou backup via Python, + envio diário para fora da VPS (Cloudflare R2/Backblaze custam centavos). Testar a restauração UMA vez.

### 7. Um engasgo da OpenAI pode congelar o app inteiro por até 10 minutos
As chamadas para a OpenAI **não têm tempo limite configurado** (o padrão do SDK é
esperar até 600 segundos). O app tem 8 "atendentes" internos (threads); 8 mensagens
presas esperando a OpenAI = painel da cozinha congela, clientes no vácuo, e o Docker
pode reiniciar o container no meio do serviço.
- **Conserto:** `timeout=10` na criação do cliente OpenAI (1 linha). Se estourar, cai no atalho por palavra-chave que já existe.

### 8. Quando algo quebra, ninguém é avisado — zero monitoramento
A chave da OpenAI expira, a Evolution cai, um erro 500 come a mensagem do cliente…
tudo morre no log do container. Você só descobre quando o dono liga furioso. E o
`/health` responde "ok" mesmo com o WhatsApp morto.
- **Conserto mínimo (1 hora):** monitor gratuito (UptimeRobot) batendo no `/health` de cada cliente + fazer o `/health` responder "não-ok" quando nenhuma mensagem chega há muito tempo em horário de funcionamento.

---

## 2. Números de WhatsApp — as respostas às suas dúvidas

**Como funciona hoje:** 1 restaurante = 1 deploy = 1 instância Evolution = **1 número
de WhatsApp exclusivo** (a "regra de ouro" do ARQUITETURA.md está correta: um número
para dois bares misturaria os pedidos).

**Quem fornece o chip? — decisão de negócio em aberto.** Não está definido em lugar
nenhum (nem código, nem docs). As opções:

| Opção | Prós | Contras |
|---|---|---|
| **Dono fornece o chip** (recomendado) | Custo zero pra você; o número "é do restaurante"; se você sumir, o número fica com ele (confiança) | Onboarding um pouco mais chato (pegar o chip dele, parear) |
| Klink compra um chip por cliente | Controle total | ~R$ 20-30/mês por cliente, logística de chip físico, esquenta no seu CPF/CNPJ; com 50 clientes vira gaveta de 50 chips |

**Risco de banimento (o ponto mais sensível):** a Evolution usa a via não-oficial do
WhatsApp. Riscos no código hoje que AUMENTAM a chance de ban:
1. **Loop do `fromMe`** (problema nº 2 acima) — rajada de mensagens = ban na hora.
2. **Limite diário**: padrão de 200 envios/dia, e quando estoura só gera um aviso num
   log que ninguém lê. Uma sexta cheia (40 mesas × ~6-10 mensagens cada) **estoura
   200 envios numa noite só**. O limite precisa subir com aquecimento gradual do chip
   e o aviso precisa chegar no SEU celular.
3. **Número novo + volume alto de cara** = perfil clássico de spam. Chip novo precisa
   de aquecimento (1-2 semanas de uso leve antes da casa cheia).
4. **Sem detecção de queda** (problema nº 1) — quando o ban acontecer, ninguém saberá.

**Várias mesas falando ao mesmo tempo com o mesmo número:** isso **funciona** — o
código diferencia cada cliente pelo telefone dele. O limite prático não é o WhatsApp,
é o processamento em fila única (1 worker, 8 threads + OpenAI sem timeout).

**Plano honesto:** Evolution serve para o piloto e os primeiros clientes. Antes de
escalar (10+ casas), migrar para a **API oficial da Meta (WhatsApp Cloud API)** —
sem risco de ban, e o custo por conversa é baixo no modelo atendimento.

---

## 3. Número das mesas — o que pode dar errado

- **Trote de casa:** o número do bot está impresso em todas as mesas. Qualquer pessoa
  **de qualquer lugar** (até de casa) manda "Mesa 7" e pede 3 picanhas — a cozinha
  prepara, e o dono ainda paga R$ 3,97 pela sessão do troll. A validação do garçom
  protege contra isso e você já a ligou no docker-compose ✅ — mas o padrão do CÓDIGO
  ainda é desligado; vale travar como ligado por padrão (à prova de esquecimento,
  como você fez com a senha do painel).
- **"Mesa 8" no meio da frase troca a mesa em silêncio:** cliente na mesa 5 pergunta
  "a mesa 8 tá livre pros meus amigos?" → a conta da mesa 5 **fecha sozinha**, abre
  sessão na mesa 8, gera nova cobrança e o painel mostra a mesa 5 livre com a família
  sentada e consumo em aberto. Conserto: só trocar de mesa com confirmação ("Você
  mudou para a mesa 8? sim/não").
- **Não existe botão de fechar mesa manualmente:** o caso mais comum no Brasil —
  cliente paga no caixa e vai embora sem pedir conta no bot — deixa a mesa "ocupada"
  no painel por até 6 horas. O dono vê 15 mesas abertas com 8 vazias no salão e perde
  a confiança no sistema. Conserto: botão "Fechar mesa" em cada cartão (a função
  `close_session` já existe pronta, falta só o botão e a rota).
- **O caixa nunca vê o TOTAL da conta:** o cliente pede "fecha a conta", o ticket
  chega no caixa… sem valor. O sistema anotou cada item com preço a noite inteira e
  na hora H o caixa soma de cabeça. É onde o produto deveria brilhar e não brilha.
- **Pedido não confirmado morre em silêncio:** cliente manda áudio, recebe
  "Confirma? 1 - Confirmar", guarda o celular no bolso achando que pediu. O rascunho
  fica pendurado pra sempre e nem o garçom consegue confirmar pelo painel. Conserto:
  lembrete automático após 2-3 min + botão de confirmação manual no painel.

---

## 4. O que quebra em produção (além dos itens do top 8)

- **Volume do banco é passo manual no Coolify:** esquecer o passo 2 do deploy =
  banco apagado a cada atualização. Conserto: o app se recusar a subir em produção
  sem o volume montado (mesmo padrão à prova de esquecimento da senha do painel).
- **Erro inesperado = cliente no vácuo + mensagem perdida PARA SEMPRE:** não há
  proteção geral de erros no processamento; pior, a mensagem é gravada antes de
  processar, então quando a Evolution reenviar, o sistema descarta como "duplicada".
  Conserto: proteção geral que responde "tive um problema, chama um atendente" + só
  considerar duplicada mensagem realmente processada.
- **Resposta do bot sem nova tentativa:** se o envio falhar, o pedido fica anotado
  mas o cliente nunca recebe a confirmação. Conserto: 2-3 tentativas + aviso no painel.
- **Deploy = 3-5 minutos surdo:** mensagens que chegam durante uma atualização do
  app são perdidas. Regra prática: nunca atualizar em horário de serviço.
- **Fuso horário:** tudo roda em UTC; a fatura "do mês" vira às 21h de Brasília do
  último dia. Menor, mas vai gerar pergunta de cliente.
- **Painel congela mudo se o wi-fi do bar cair:** a equipe acha que está tranquilo
  enquanto chovem pedidos no servidor. Conserto: tarja vermelha "SEM CONEXÃO".

---

## 5. Cobrança e dinheiro

- **A trava dos R$ 147 não trava nada:** a conta de demonstração já nasce "ativa"
  com setup marcado como pago. Cliente real começa a usar sem nunca ter pago o setup,
  e não fica rastro em fatura nenhuma. Conserto: cliente real nasce "aguardando
  setup" e só ativa quando o Pix cair.
- **Receber é 100% manual:** a fatura é um número no banco; você gera com um comando
  manual, recebe o Pix por fora e marca como paga com outro comando. Sem vencimento,
  sem corte automático de inadimplente. Funciona para 3 clientes; não para 30.
- **Sem extrato detalhado:** se o dono disser "não abri 80 mesas, abri 60", hoje não
  há relatório que prove (qual mesa, que horas). Conserto: tela de extrato simples —
  data, hora, mesa, valor.
- **A conta de viabilidade que você precisa fazer ANTES de vender:**
  - Restaurante de 30 mesas, 1,5 giro/noite, 25 dias = ~1.125 aberturas/mês ≈
    **R$ 4.466/mês** — mais caro que um garçom CLT (e isso assumindo 1 celular por
    mesa; com o problema nº 3, pode dobrar).
  - Boteco de 15 mesas, 1 giro, 26 dias = ~390 aberturas ≈ **R$ 1.548/mês**.
  - O preço por mesa aberta pune o cliente que dá certo. Vale estudar: **teto mensal**
    (ex.: "no máximo R$ 397/mês"), planos por faixa, ou preço fixo por mesa física.
- **Deixar claro no material de venda:** o Klink **anota** o pedido; quem cobra o
  jantar é o caixa do restaurante. Hoje isso não está dito em lugar nenhum e o dono
  pode achar que o sistema recebe pagamento.

---

## 6. Como vender sem tablet na cozinha/bar — a resposta

**A solução está 90% pronta no seu código e custa zero em equipamento.**

O Klink já sabe mandar mensagem de WhatsApp para qualquer número (é o que ele faz
com o cliente o tempo todo). Falta só:

1. Um campo **"WhatsApp da cozinha"** (e opcionalmente "do bar" e "do caixa") na tela
   de Configurações;
2. Depois que o cliente confirma o pedido, mandar a comanda formatada para esse
   número ou para um **grupo** de WhatsApp:

   > 🍽️ **MESA 12** — 21h03
   > 2x Picanha acebolada (sem cebola)
   > 1x Brahma 600
   > Total parcial: R$ 86,50

3. Na cozinha: **um celular velho pendurado na parede** com o WhatsApp aberto. O
   WhatsApp já apita sozinho — resolve também o problema do alerta sonoro.

**Vira o argumento de venda, não uma limitação:** *"O pedido cai no WhatsApp da sua
cozinha, no celular que você já tem. Não precisa comprar nada."* O painel web vira
complemento (visão geral do salão, fechar mesa), não pré-requisito.

É ~1 dia de trabalho. Atenção apenas: cada comanda enviada consome 1 mensagem do
limite diário da Evolution (mais um motivo para subir o limite de 200).

**Fase 2 (casas maiores):** impressora térmica de comanda (como o iFood usa, ~R$
250-400 o equipamento). Hoje não existe nada disso no código — fica para quando
tiver 10+ clientes pedindo.

---

## 7. O que mais ninguém tinha visto (achados extras)

- **O cliente não tem cardápio nem preço em lugar nenhum** — o QR joga direto pro
  WhatsApp, e perguntar "qual o cardápio?" chama um atendente. Conserto barato: o bot
  responder o cardápio em texto, ou o QR apontar para uma paginazinha com cardápio +
  botão "pedir no WhatsApp".
- **Garçom não consegue lançar pedido pelo painel** — mesa sem WhatsApp (idoso,
  celular morto, sem sinal dentro do salão) fica fora do sistema e a conta da mesa
  fica incompleta.
- **"Sem cebola" se perde no caminho de emergência** — quando a OpenAI falha, o
  atalho por palavra-chave ignora as observações do cliente. E as observações nunca
  são confirmadas de volta.
- **Cancelamento não existe** — nem o cliente cancela pedido confirmado, nem o
  cliente fica sabendo quando a cozinha cancela um item.
- **Produto sem "apelidos" fica invisível no modo de emergência** — se o dono
  cadastrar "Cerveja Heineken 600" sem apelidos e a OpenAI estiver fora, o bot não
  reconhece "uma heineken".
- **Sem nota fiscal e sem integração com o PDV** que o restaurante já usa — todo
  pedido vira redigitação no caixa. Para começar, posicionar como "comanda
  digital" e ser honesto sobre isso.
- **LGPD:** telefone + histórico completo de consumo guardados para sempre, sem
  política de privacidade (os links na landing estão mortos) e sem rotina de
  exclusão. Risco real para um produto que guarda conversa de consumo de bar.
- **Sem horário de funcionamento:** o bot abre mesa, cobra R$ 3,97 e diz "já mandei
  pra cozinha" às 3h da manhã com a casa fechada.
- **Sem relatório de vendas:** o dono não sabe nem quanto vendeu hoje — informação
  que até o bloquinho dava. (Os dados todos já estão no banco; falta uma tela.)
- **Taxa de serviço (10%), couvert, meia porção, combo, happy hour:** não existem.
- **"Manda 100 picanhas" entra na fila sem alarme** — falta um teto de quantidade.
- **Uma senha só para todo mundo:** o cozinheiro vê a fatura e pode apagar o cardápio.

---

## 8. Plano de ação priorizado

**Agora (antes de QUALQUER venda) — 2 a 4 dias de trabalho:**
1. ✅ ~~Filtro `fromMe` (5 linhas — elimina o pior cenário de banimento)~~ **FEITO em 09/06/2026.**
2. ✅ ~~Timeout de 10s na OpenAI (1 linha)~~ **FEITO em 09/06/2026.**
3. ✅ ~~Comanda por WhatsApp para a cozinha (1 dia — destrava a venda sem tablet)~~ **FEITO em 09/06/2026.**
4. ✅ ~~Tela de cadastro de mesas (sem ela o produto não cabe em nenhum restaurante real)~~ **FEITO em 09/06/2026.**
5. ✅ ~~Botão "Fechar mesa" manual no painel~~ **FEITO em 09/06/2026.**
6. ✅ ~~Backup que funciona + cópia diária fora da VPS + testar restauração 1 vez~~ **FEITO em 09/06/2026** (falta só você rodar o teste de restauração 1 vez, ver DEPLOY.md).

**Semana seguinte (antes do primeiro cliente pagante):**
7. Cobrança por mesa física (não por celular) — ou, no mínimo, avisar o preço real.
8. Total da conta no ticket do caixa + extrato pro cliente no WhatsApp.
9. Detecção de WhatsApp desconectado + aviso no seu celular + selo honesto no painel.
10. Monitor de uptime gratuito no `/health` de cada cliente.
11. Proteção geral de erros (responder "chama um atendente" em vez de silêncio).
12. Conta de cliente real nasce "aguardando setup" (trava dos R$ 147 de verdade).

**Antes de escalar (10+ clientes):**
13. Migrar para a API oficial da Meta (elimina risco de ban).
14. Rever modelo de preço (teto mensal ou planos).
15. Página de cardápio pro cliente + pedido manual pelo garçom.
16. Política de privacidade + retenção de dados (LGPD).
17. Relatório de vendas para o dono.
