# Progresso — Klink

> Diário de bordo do projeto, em linguagem simples. Atualizado a cada mudança.
> Última atualização: **15/06/2026**

---

## O que é o app

Um **garçom invisível dentro do WhatsApp** para bares e restaurantes.

O cliente senta na mesa, escaneia um QR Code, manda mensagem ("Mesa 12") no
WhatsApp do estabelecimento e começa a pedir por texto ou áudio. O pedido
cai num painel kanban dividido por setor (Bar, Cozinha, Salão, Caixa) que
o garçom acompanha pelo computador/celular.

**Cobrança do nosso lado:** R$ 147 de setup + **R$ 3,97 por mesa aberta**.

---

## Status atual

| Item | Situação |
|------|----------|
| Código | Pronto e rodando |
| Repositório | https://github.com/jaolito85-hash/whatsmesa (público) |
| Servidor | Coolify, na sua VPS |
| URL do app | `https://g7yafnc904l4nk0rkfibx6fa.72.60.13.166.sslip.io` |
| WhatsApp (Evolution) | URL configurada, falta API Key + número |
| Testes automáticos | 460/460 passando ✅ |
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

- [ ] 🚨 **URGENTE — Desligar o KLINK_DEV_MODE no Coolify (12/06/2026).** O João
  ligou o "dev mode" no Coolify tentando rodar o app no computador local (não
  precisava — Coolify só vale pro servidor). Com ele ligado NO SERVIDOR, as rotas
  de administração ficam abertas sem senha pra qualquer pessoa na internet.
  No Coolify: apagar a variável `KLINK_DEV_MODE` (ou deixar `=0`) e garantir que
  `KLINK_DASHBOARD_PASSWORD` tem uma senha forte. Pra teste no computador local,
  o dev mode é ligado só na janela do PowerShell: `$env:KLINK_DEV_MODE = "1"`.
- [x] ✅ **QR permanente — RESOLVIDO (31/05/2026).** Agora cada mesa tem um "endereço
  fixo" que nunca muda, então o **QR impresso e colado continua funcionando para sempre**
  (inclusive depois da conta fechar e a mesa reabrir). A proteção interna do link
  dinâmico foi mantida intacta — não removi nenhuma segurança. **Pode colar QR em mesa
  de verdade.**
- [x] ✅ **Validação do garçom ligada por padrão (31/05/2026).** Já deixei
  `KLINK_REQUIRE_TABLE_VALIDATION=true` no docker-compose e no .env.example. É o que
  blinda o QR permanente (mesa só abre depois que o garçom confirma no painel). Confira
  se está ligada também no Coolify.
- [ ] Definir nome final (Klink ou outro). Verificar marca registrada no INPI classes 9 (software) e 43 (restaurante).
- [ ] Comprar `klink.app` adicional (~US$ 8) pra travar a marca.
- [ ] Trocar o ícone do WhatsApp na logo (usar literalmente o logo da Meta = risco de processo).
- [ ] Pegar API Key + nome da instância da Evolution e botar no Coolify.
- [ ] Pegar o número de WhatsApp do garçom (chip dedicado de preferência).
- [ ] Cadastrar o primeiro restaurante de verdade (substituir o "Klink Demo" pelo nome real do estabelecimento). → **Já dá pra fazer sozinho** na tela **Configurações** do painel.
- [ ] Trocar a foto stock do painel pela foto real do estabelecimento.

---

## Histórico — o que foi feito (mais recente primeiro)

### 15/06/2026 (noite) — Modo Painel: a tela de pedidos da cozinha/bar (tipo totem)
- **A ideia:** os pedidos não devem chegar em conversa de WhatsApp pra equipe (vira
  bagunça). Precisava de uma tela dedicada na cozinha/bar, atualizando sozinha, tipo
  um totem de praça de alimentação.
- **A descoberta:** o painel que já existe (`/dashboard`) já tinha tudo por dentro —
  separa por setor, atualiza a cada 4 segundos e apita quando chega pedido. Faltava só
  uma "casca" feita pra tela de cozinha. Aproveitei 100% disso.
- **O que criei — o "Modo Painel" (`/painel`):** uma tela cheia, fundo escuro, letras
  grandes pra ler de longe. Ao abrir, ela pergunta **"Qual tela é esta?"** e você escolhe
  o setor (Cozinha, Bar, Salão, Caixa ou Tudo junto). Daí mostra só os pedidos daquele
  setor, em comandas grandes, com um botão gigante (ex.: "Começar 👨‍🍳" → "Pronto ✓").
  O aparelho **lembra** o setor escolhido. Apita a cada pedido novo. Mostra tarja
  vermelha se a internet cair. Tem relógio e contador de pedidos.
- **Vira "app" no tablet (PWA):** dá pra **instalar** no tablet/celular como se fosse um
  aplicativo (ícone na tela, abre em tela cheia, sem a barra do navegador). No iPad é só
  "Adicionar à Tela de Início"; no Android, "Instalar app". Importante: a tela **nunca**
  mostra pedido velho de cache — pedido é sempre puxado ao vivo.
- **Onde achar:** tem um atalho **"Modo Painel 🖥️"** no topo do painel normal. Ou abrir
  direto `klinkai.com.br/painel` num tablet na cozinha.
- **Segurança:** é tela interna, exige o login do painel (o mesmo seu). Confirmado por teste.
- **Testado de verdade:** subi o sistema, simulei um pedido caindo e tirei foto das telas —
  a comanda apareceu certinha na Cozinha, e o Bar mostrou "nenhum pedido". 460 testes OK.
- **Próximo passo possível (quando quiser):** impressora térmica pra quem prefere a comanda
  de papel na cozinha. Deixei anotado, mas começamos pela tela porque é custo zero.

### 15/06/2026 (noite) — Correção: dava pra colocar apelido na mesa, mas não tirar
- **O bug:** na tela de QR codes, ao usar "renomear" e digitar um apelido (ex.: "Varanda 3"),
  o nome ficava preso — se você apagasse o texto e clicasse OK, não acontecia nada. Não
  tinha como voltar a mesa pro nome simples "Mesa 3".
- **Por que acontecia:** tanto o navegador quanto o servidor rejeitavam nome em branco.
- **Correção:** agora, deixar o campo em branco e clicar **OK apaga o apelido** e a mesa
  volta a ser só "Mesa 3". Clicar em **Cancelar** continua não mexendo em nada. A janelinha
  de renomear agora já vem com o apelido atual (vazio se a mesa não tiver apelido) e explica
  que apagar volta ao padrão.
- **Detalhe que confunde, mas é proposital:** o "MESA 3" não some quando você põe um apelido.
  O número é o que o cliente usa pra abrir a mesa no WhatsApp ("Mesa 3"); o apelido
  ("Varanda 3") aparece junto, só pra equipe se localizar no salão.
- Testado de ponta a ponta. 460 testes passando (atualizei o teste antigo que esperava o
  comportamento errado).

### 15/06/2026 — Área do Vendedor protegida por senha (`klinkai.com.br/vendedores`)
- **O que pediu:** uma página na web, com login e senha, pra mandar pros vendedores
  que vão nos bares vender o Klink.
- **O que fiz:** o Kit de Vendas (apresentação + guia) agora fica no ar dentro do seu
  próprio site, atrás de uma tela de login. O vendedor abre **`klinkai.com.br/vendedores`**
  no celular, digita a senha da equipe **uma vez**, e o material abre. Fica logado por
  30 dias, então não precisa digitar senha toda hora na rua.
- **Segurança (o ponto mais importante):** essa senha é **separada** da sua senha de
  dono. Quem tem a senha do vendedor vê **só** o material de vendas — nunca o painel,
  a cobrança nem as configurações. Testei: a senha do vendedor é barrada no painel.
- **Como você define a senha:** no Coolify, crie a variável `KLINK_VENDEDOR_PASSWORD`
  com a senha que quiser (ex: `copa2026`). Pra trocar (quando alguém sai da equipe),
  é só mudar essa variável. Sem ela preenchida, a área fica desligada.
- **Pra ficar mais seguro ainda:** defina também `KLINK_SECRET_KEY` com um texto longo
  e aleatório (assina o "crachá" de login). Sem ela, o sistema usa a senha do painel
  como base — funciona, mas o ideal é ter a própria.
- **Falta só:** subir pro Coolify (deploy) e criar a variável da senha. Aí o link
  funciona. Todos os 460 testes continuam passando.

### 12/06/2026 — Apresentação de vendas em arquivo único (imagens não quebram mais)
- Problema: ao enviar `material-vendas/apresentacao.html` sozinho, as imagens não
  abriam (ficavam na pasta `img/` que não ia junto).
- Solução: script `scripts/empacotar_apresentacao.py` que gera
  **`material-vendas/Klink-Apresentacao.html`** — um arquivo único (1,6 MB) com o
  CSS e as imagens embutidos (data URI). Abre perfeito em qualquer celular/computador,
  até sem internet, sem precisar de pasta nenhuma junto.
- O botão "Quero testar no meu bar" agora leva ao WhatsApp oficial
  (`wa.me/554431011918`). Se um dia quiser número por vendedor, é só ajustar o script.
- Testado de verdade: copiei o arquivo sozinho pra uma pasta vazia e abri — as 3
  imagens carregaram, zero requisição externa, mobile sem estouro.

### 12/06/2026 — Número de WhatsApp real nos botões da landing
- Os 4 botões de ação ("Começar Agora" no topo, "Quero testar no meu restaurante"
  no hero, na seção de preços e no fechamento) agora apontam para o WhatsApp real:
  **+55 44 3101-1918** (`wa.me/554431011918`), com mensagem pronta e abrindo em
  nova aba. O número de mentira (5511999999999) saiu de vez.
- ⚠️ Conferir: esse número parece ser **fixo** (prefixo 31xx). O link `wa.me` só
  abre conversa se o número tiver **WhatsApp ativo** (Business funciona em fixo).
  Vale o João mandar um "oi" pelo próprio link pra confirmar que abre a conversa.

### 12/06/2026 — Termos de Uso e Política de Privacidade no ar (LGPD)
Os botões "Termos" e "Privacidade" do rodapé deixaram de ser enfeite:
- **Páginas novas** `/termos` e `/privacidade`, públicas, no mesmo visual da marca.
- **Política de Privacidade conforme a LGPD**: quem é controlador e quem é operador
  (detalhe importante: nos dados do cliente da mesa, o restaurante é o controlador
  e o Klink é o operador), tabela do que é coletado de cada pessoa, finalidades,
  áudio processado por IA só pra montar o pedido, com quem compartilha, prazos de
  guarda, direitos do titular (art. 18) com canal de contato e menção à ANPD.
- **Termos de Uso honestos**: o que o serviço é (e o que NÃO é), fase piloto,
  preços por extenso (R$ 147 únicos + R$ 3,97 por mesa validada, sem mensalidade),
  dependência do WhatsApp declarada, cancelamento sem multa, foro do domicílio
  do estabelecimento (amigável ao pequeno).
- 2 testes novos garantem que as páginas são públicas — **460 testes passando**.
- ⚠️ Pendência anotada: quando o Klink tiver CNPJ/razão social, incluir nos dois
  documentos. E antes de escalar pra muitos clientes, vale revisão de advogado.

### 12/06/2026 — Hero com iPhone animado (mini-vídeo) no lugar do card de chat
O card de conversa do topo virou um **iPhone realista desenhado na própria página**,
com o WhatsApp do Klink aberto:
- Foto de perfil = mascote real do Klink, nome "Klink" com **selo azul de verificado**,
  status "online", barra de status com hora/sinal/bateria e a "ilhinha" do iPhone.
- A conversa **se mexe sozinha em loop**, como um mini-vídeo: cliente manda **áudio**
  (bolha com onda sonora animada) → "digitando..." → Klink entende ("🍺 3 Coronas ·
  🍟 2 batatas. Confirma?") → cliente responde "1" → **"Pedido enviado! ✅ O Bar e a
  Cozinha já receberam. Já já chega na sua mesa 😉"**.
- Vantagens sobre vídeo de verdade: texto 100% nítido, não pesa nada no carregamento
  e é grátis. O mascote grande continua no canto esquerdo, intocado.
- Ajuste de copy a pedido do João: "Nada muda no seu salão" virou **"Nada muda na
  sua operação. Você só vende mais."** — com a palavra "vende" em verde-dinheiro.
- **Vistoria completa no celular** (telas de 360px e 390px): o teste automático achou
  2 defeitos e os dois foram corrigidos na hora — (1) a página "vazava" 4 pixels pro
  lado no Android por causa do quadro verde inclinado atrás do iPhone (agora qualquer
  decoração que escape é cortada, sem rolagem lateral); (2) no celular, o logo
  atropelava o link "Entrar no Painel" na barra do topo (o link agora só aparece em
  tela grande — no celular fica logo + botão "Começar Agora" em uma linha).
  Reverificado depois das correções: zero estouro, zero erro, as 9 seções na ordem
  certa e nada cortado.
- Também foi gerada **1 imagem no Higgsfield** (iPhone fotorrealista na mão, em mesa
  de bar, com o mascote no perfil, tick azul e texto em português PERFEITO). O João
  avaliou e decidiu: **o iPhone animado fica no topo do site**; a foto foi guardada em
  `material-vendas/criativo-iphone-whatsapp.png` — é um criativo pronto pros anúncios
  do plano de tráfego pago. Vídeo de IA fica pra depois, se precisar.

### 11/06/2026 (tarde) — Landing page versão "vendedora": copy agressiva + calculadora
Segunda rodada na página, agora com copy comercial de verdade (visual preservado):
- **Título**: mantido "O seu WhatsApp agora atende as mesas." (escolha do João,
  com a palavra "WhatsApp" em verde) — e a linha "Sem app. Sem login. Sem mudar
  sua operação." logo abaixo do botão.
- **Dor com nome e sobrenome**: "A venda não se perde no caixa. Ela se perde na
  espera." + os 3 blocos (cliente já sabe o que quer / garçom não está em todas /
  pedido que espera, esfria). Cita quiosque, praia e área externa.
- **Como funciona virou 5 passos**, terminando em "Cai no setor certo" (Bar,
  Cozinha, Caixa, Salão). Banido o "nossa IA entende" — agora é "o Klink entende".
- **Seção nova de exemplos**: 6 cartões mostrando a mensagem do cliente virando
  etiqueta de setor ("Me vê 3 Coronas e 2 batatas" → Bar + Cozinha; "fecha minha
  conta" → Caixa; "pode limpar?" → Salão; inglês e espanhol → chegam em português;
  áudio no meio do barulho).
- **Calculadora interativa**: "Quanto vale um pedido extra por mesa?" — o dono
  arrasta 4 controles (mesas/dia, pedidos extras/dia, valor médio, dias/mês) e vê
  na hora: venda adicional, custo do Klink e a diferença que sobra. Com aviso
  honesto de "simulação ilustrativa" — zero promessa de porcentagem inventada.
- **Fechamento novo**: faixa escura no fim — "Seu cliente está com o celular na
  mão agora" — com botão pro WhatsApp.
- Botões agora dizem "Quero testar no meu restaurante".
- **Conferido**: foto da página em tela de computador e de celular (tudo
  empilha certinho no celular), calculadora testada ao vivo (conta bate) e os
  **458 testes passando**.

### 11/06/2026 — Landing page com nova abordagem de venda (visual intacto)
O design (cores, fontes, estilo) ficou igual — só a conversa mudou, agora toda
focada no dono de restaurante/bar e no "você não tem risco nenhum":
- **Título novo**: "Mesa que não espera consome mais." — fala de dinheiro logo
  na primeira frase.
- **Zero mensalidade em todo lugar**: no topo, na seção de preços (agora o
  R$ 0,00 aparece GRANDE e em verde antes dos outros valores) e nas dúvidas.
  Mensagem: se nenhum cliente abrir mesa, a conta do mês é R$ 0,00.
- **R$ 3,97 por mesa aberta** com a explicação que convence: a mesa gastou
  R$ 100, R$ 300 ou R$ 500? Tanto faz, são os mesmos R$ 3,97.
- **R$ 147 com o que vem dentro**: a gente fornece o número de WhatsApp,
  instala todo o programa, cadastra o cardápio e entrega os QR Codes prontos.
- **A cena da mão levantada**: cliente que já sabe que quer 3 cervejas não tem
  por que ficar de braço erguido esperando o garçom olhar. Virou a seção escura
  do "problema".
- **A fala do garçom** entrou no "como funciona": "se você me chamar e eu
  estiver em outra mesa, pede pelo QR que sai na hora" — deixando claro que
  nada muda na operação e ninguém é substituído.
- **Nova seção "Dúvidas de dono de bar"**: mata as 4 objeções (preciso mudar
  algo? não tenho cardápio online; precisa baixar app? e se ninguém usar?).
- **Honestidade**: removi os "+12 restaurantes pilotos" com fotos falsas de
  banco de imagem — no lugar, o convite real: piloto aberto pra poucos
  restaurantes.
- Conferi a página inteira com captura de tela: nada quebrou no visual.

### 10/06/2026 — Playbook de tráfego pago pronto (`TRAFEGO_PAGO.md`)
Plano completo para anunciar o Klink e fazer donos de bar chamarem no WhatsApp:
- **Estratégia**: anúncio em vídeo no Instagram/Facebook → clique cai no WhatsApp de
  vendas → demo ao vivo em 2 minutos → piloto de R$ 147.
- **Campanhas**: validação com R$ 30/dia (clique-para-WhatsApp, 2 públicos, 3 criativos),
  remarketing na semana 3 e regras de escala.
- **4 criativos roteirizados** (demo crua filmada no bar, fundador na câmera, imagem
  "R$ 3,97 por mesa" e carrossel) + **3 copys prontas** com títulos e botão.
- **Roteiro de atendimento do lead** (responder em 5 min, qualificar, demo ao vivo
  pelo número demo, proposta e objeções) + metas honestas (3 a 8 pilotos no 1º mês).
- 19 commits da auditoria também foram **enviados ao GitHub** hoje (deploy liberado).

### 09/06/2026 — Segunda leva: as 8 correções estruturais (todas prontas!)
A continuação da auditoria, com as mudanças mais profundas:
1. **Cobrança por mesa física, não por celular** 🏆 — 4 amigos escaneando o QR da
   mesma mesa agora é UMA cobrança de R$ 3,97 (antes eram 4 — fatura até 4x maior
   que o prometido). E a mesa só libera quando a última comanda fecha.
2. **Troca de mesa só explícita** — "a mesa 8 tá livre?" não fecha mais a conta da
   mesa 5 em silêncio.
3. **Conta com total** — o caixa vê o valor no ticket e o cliente recebe o extrato
   itemizado no WhatsApp.
4. **WhatsApp caído agora grita** — selo honesto na config, banner vermelho no
   painel e alerta no /health para monitor gratuito avisar o celular do fundador.
5. **Webhook blindado** — erro inesperado responde "chama um atendente" em vez de
   silêncio, e mensagem não se perde mais para sempre.
6. **Trava real dos R$ 147** — cliente real só usa depois do setup pago (e as mesas
   de teste da demo viram cortesia, fora da fatura). Fatura sem buracos e mês
   virando no fuso de Brasília.
7. **Painel vivo** — bip de campainha em comanda nova, tarja "SEM CONEXÃO" quando o
   wi-fi cai, e botão pro garçom destravar rascunho de cliente que não respondeu "1".
8. **Bot melhor** — responde o cardápio com preços (3 idiomas), teto anti-trote de
   30 unidades por item, e texto honesto pós-confirmação.
- Tudo passou por **nova revisão dupla** (segurança + caça-bugs): 3 bugs achados e
  corrigidos na hora (o pior: a primeira fatura cobraria os testes da demo).
- **458 testes passando** (eram 367 de manhã). 17 commits no dia.
- **➡️ O passo a passo do que falta fazer (deploy, monitores, backup) está no novo
  `PRONTO_PARA_PRODUCAO.md`.**

### 09/06/2026 — As 6 correções urgentes da auditoria (todas prontas!)
Implementei os 6 itens do "antes de QUALQUER venda" do plano da auditoria:
1. **Filtro anti-loop no WhatsApp** — o bot não responde mais a si mesmo (era o
   maior risco de banimento do número). Também ignora grupos e eventos de sistema.
2. **Tempo limite na OpenAI** — um engasgo da IA não congela mais o app inteiro:
   em 10 segundos o bot cai no atalho por palavra-chave e responde mesmo assim.
3. **Botão "fechar mesa" no painel** — para o caso mais comum: cliente paga no
   caixa e vai embora sem avisar o bot. A grade de mesas agora atualiza sozinha.
4. **Cadastro de mesas** — acabou a prisão das 12 mesas da demo: "meu salão tem
   40 mesas" cria tudo em lote, com QR na hora; dá pra renomear e remover.
5. **Comanda no WhatsApp da cozinha** 🏆 — a resposta da venda sem tablet: novo
   campo nas Configurações; pedido confirmado chega formatado (itens, "sem
   cebola", total) no celular da cozinha, que apita sozinho. Pedido de conta e
   chamados também avisam a equipe.
6. **Backup de verdade** — o comando do manual não funcionava (programa não
   instalado); corrigi a imagem, criei a rota segura `/admin/backup` para baixar
   o banco de fora da VPS, e o DEPLOY.md agora tem backup em 3 passos com teste
   de restauração. De quebra: os comandos `/admin/*` do manual estavam sem a
   senha do painel e falhariam em produção — corrigido.
- Depois de pronto, passei tudo por **duas revisões independentes** (segurança +
  caça-bugs): nada crítico; os 7 achados menores foram corrigidos na hora (validação
  do WhatsApp da equipe, filtro de transmissões/canais, simulador sem WhatsApp real,
  e proteções contra cliques duplos e corridas no cadastro de mesas).
- **48 testes novos — 415 passando** (eram 367). Veredito da revisão de segurança:
  **pode ir para produção**.

### 09/06/2026 — Auditoria de operação completa (visão de dono de restaurante)
- Rodei uma auditoria profunda com 44 agentes de análise, cada falha grave checada
  por um segundo agente cético. Resultado: **38 falhas graves confirmadas** +
  15 pontos novos. Relatório completo em **`AUDITORIA_OPERACAO.md`**.
- **Os 3 mais perigosos:** (1) se o WhatsApp cair, ninguém fica sabendo — o selo
  "Bot conectado" do painel mente; (2) o bot pode responder a si mesmo e entrar em
  loop infinito (= banimento do número) — conserto de 5 linhas; (3) a cobrança é por
  **celular**, não por mesa — 4 amigos escaneando o QR = 4 × R$ 3,97 numa mesa só,
  fatura até 4x maior que o prometido.
- **Resposta da venda sem tablet:** mandar a comanda por WhatsApp para um celular
  velho na cozinha — a infraestrutura já existe no código, falta ~1 dia de trabalho.
  Vira argumento de venda: "o pedido cai no celular que você já tem".
- **Outras descobertas importantes:** não existe cadastro de mesas (preso às 12 da
  demo), o backup documentado não funciona (programa não instalado no container),
  não existe botão de fechar mesa manual, e o caixa nunca vê o total da conta.
- O plano de ação priorizado (o que fazer antes de vender) está na seção 8 do
  relatório. **Nada foi alterado no código ainda** — só análise.

### 31/05/2026 — Tela de Cardápio + fechar mesa mais claro
- **Nova tela de Cardápio** (atalho no painel): o dono cadastra/edita/remove produtos
  sozinho — nome, preço, setor (Bar/Cozinha) e os **apelidos** (as formas que o cliente
  fala, ex: "gelada", "breja" → cerveja). É o que o bot usa pra reconhecer os pedidos.
  Antes o cardápio era fixo no código; agora é self-service.
- **Fechar mesa mais claro:** no caixa, o botão da conta agora diz **"Fechar mesa 💰"**
  em vez de "concluída". Ao clicar, a mesa fecha e o **QR continua valendo** pro próximo
  grupo (não precisa fazer nada com o QR).
- Cobri com testes (inclusive provando que um produto cadastrado com apelido é
  reconhecido pela IA no pedido). **367 testes passando.**

### 31/05/2026 — Guia de deploy atualizado (pronto pro primeiro cliente)
- Reescrevi o **`DEPLOY.md`** completo e atualizado: passo a passo do Coolify com
  subdomínio por cliente, o **webhook com segredo**, validação do garçom ligada,
  preço correto (setup 147 + 3,97/mesa), smoke test que prova que o webhook está
  protegido, e o checklist de segurança.
- Começamos o **primeiro deploy guiado** (ver conversa).

### 31/05/2026 — Segunda leva de segurança (fechando as brechas restantes)
- **Senha do painel agora é obrigatória de verdade:** em produção, se esquecer de
  configurar a senha, o sistema **se recusa a ligar** (antes era só um aviso). À prova
  de esquecimento.
- **Mesa rejeitada não gera mais cobrança "fantasma":** o garçom só consegue recusar uma
  mesa que ainda está *aguardando confirmação* (não uma que já foi aberta e cobrada).
- **Faturas à prova de clique duplo:** gerar ou marcar como paga duas vezes não quebra
  nem cobra de novo.
- **Barreira anti-invasão no áudio:** o sistema se recusa a baixar áudio de endereços
  internos suspeitos (proteção extra além do webhook).
- **Aviso forte** se o "modo de desenvolvimento" ficar ligado por engano em produção.
- Tudo coberto por **mais 10 testes** — total agora **361 passando**. Atualizei o
  `SEGURANCA.md`: a lista de "antes do 2º cliente" está zerada; só restam itens de
  maturidade (LGPD/retenção de dados) pra quando escalar.

### 31/05/2026 — Auditoria de segurança + webhook blindado
- Rodei uma auditoria de segurança completa antes de ligar pra valer. Achei **3 buracos
  críticos** e **corrigi todos**:
  1. **O webhook estava aberto** — qualquer um na internet podia forjar pedidos e gerar
     cobrança falsa no bar. Agora ele exige um **segredo** (`KLINK_WEBHOOK_SECRET`) pra
     aceitar mensagem. Sem o segredo certo, ignora. 🛡️
  2. O "simulador de mensagens" (usado só em teste) ficava acessível — **bloqueei em
     produção**.
  3. Desliguei um modo de debug perigoso e botei um **aviso forte** se alguém esquecer
     de configurar a senha do painel.
- Confirmei o que já estava bom: **nada de senha/chave vaza pro navegador** e a
  **cobrança não duplica**.
- O resto dos achados (menores) ficou anotado em ordem de prioridade no novo
  **`SEGURANCA.md`**.
- **Sobre trocar a API do WhatsApp:** por enquanto seguimos com a **Evolution** (barata e
  rápida) com o webhook já blindado. **Antes de escalar pra muitos bares**, vale migrar
  pra **API oficial da Meta** (não corre risco de o número ser banido). Detalhes no
  `SEGURANCA.md`.
- **351 testes passando** (8 novos só de segurança).

### 31/05/2026 — Decisão de arquitetura: como atender vários restaurantes
- Auditei a segurança do site: **nada de senha ou chave de API fica no navegador**
  (tudo no servidor). O painel fica atrás de senha. ✅
- Decidimos o caminho pra produção: **"uma instalação por restaurante"** (cada bar tem
  seu subdomínio, sua senha e seu número de WhatsApp). É seguro, já funciona hoje e não
  exige reescrever nada — perfeito pro piloto e pra Copa.
- O **multi-tenant de verdade** (uma URL só, cada bar logando com sua senha) fica pra
  quando tivermos ~20–30 clientes — é um projeto à parte, arriscado de apressar.
- Escrevi tudo no novo **`ARQUITETURA.md`**: passo a passo pra subir cada cliente,
  domínios/DNS (incl. `app.klinkai.com.br`), checklist de segurança e o plano do futuro.

### 31/05/2026 — QR das mesas agora é permanente (não quebra mais)
- **O problema:** o QR colado na mesa parava de funcionar depois que a conta fechava,
  porque o sistema trocava o "código interno" dele. No bar real, o segundo grupo veria
  "QR inválido". Inviabilizava colar QR fixo na mesa.
- **A solução (sem remover segurança):** dei a cada mesa um **endereço fixo** (que nunca
  muda) pro QR impresso usar. O link dinâmico interno continua trocando como antes — não
  tirei nenhuma proteção. Agora o QR colado vale **para sempre**, mesmo abrindo e
  fechando a mesa a noite toda.
- **Blindagem:** deixei a **validação do garçom ligada por padrão** (mesa só abre depois
  que alguém confirma no painel). É isso que protege o QR permanente.
- Testado de ponta a ponta: o link redireciona certo antes e depois de fechar a mesa.
  **343 testes passando** (incluindo 5 novos só pra esse caso).

### 30/05/2026 — Kit de Vendas pro tio apresentar (HTML bonitão)
- Criei o **Kit de Vendas Klink** na pasta `material-vendas/` — 3 páginas web lindas,
  feitas pra abrir no celular dentro do bar:
  1. **index** — capa que organiza as duas peças.
  2. **apresentacao** — o pitch que o tio MOSTRA pro dono (problema da Copa, como
     funciona, ROI, preço/risco zero, CTA).
  3. **guia-do-vendedor** — o manual SÓ do tio: como funciona por dentro, o ciclo da
     mesa (abre/valida/fecha/reabre), segurança, como cadastrar + QR codes, a
     matemática da venda, script de abordagem, resposta pra toda objeção e FAQ.
- Tudo no visual da marca (verde, mascote, fonte) e com a pegada da Copa.
- Conferi cada página em tela de celular (screenshots) e corrigi um detalhe de
  formatação nas listas. Está pronto pra enviar.
- ⚠️ Achei um ponto técnico importante lendo o código — veja o item **CRÍTICO**
  na lista de pendências abaixo (sobre os QRs depois que a mesa fecha).

### 29/05/2026 — Sai o "MesaZap Demo"; preço correto (3,97 por mesa)
- No painel, enquanto o restaurante **não tem nome configurado**, agora aparece só a
  **logo do Klink** (não mais "MesaZap Demo" nem "Klink Demo"). Quando você cadastra o
  nome nas Configurações, o painel passa a mostrar **o nome do restaurante**.
- O "MesaZap Demo" e o preço antigo de **R$ 1,97** estavam **gravados no banco do
  servidor** (não no código). Criei uma **correção automática** que roda toda vez que o
  sistema sobe: troca "MesaZap Demo" por Klink e o preço **1,97 → 3,97**. Então, no
  próximo deploy no Coolify, o servidor se corrige sozinho — sem mexer em banco à mão.
- Acertei os textos de cobrança: agora falam **"R$ 3,97 por mesa aberta"** (antes diziam
  "R$ 1,97" e "por pedido") no painel e no resumo de cobrança.
- Alinhei os valores-padrão de cobrança em todos os cantos do sistema (3,97 + setup 147).
- Cobri tudo com **testes novos** (9) e a suíte segue verde: **338 ok**.

### 29/05/2026 — Tela de Configurações + página de QR codes
- Agora dá pra **cadastrar o restaurante do cliente sozinho**, sem mexer em banco:
  no painel tem o atalho **Configurações**, com campos de **Nome do restaurante**
  e **WhatsApp do bot**. É só preencher e clicar em "Salvar alterações".
- O número de WhatsApp salvo ali passa a ser o número que **os QR codes abrem** —
  antes isso dependia de configuração técnica no servidor.
- Nova página **QR codes das mesas** (atalho no painel): mostra um cartão lindo por
  mesa, com o QR pronto, o número da mesa e a marca Klink. Tem botão **Imprimir** que
  gera uma folha organizada (2 por linha, encaixa no A4) pra recortar e colar nas mesas.
- Se ainda não tiver número configurado, a página avisa em amarelo e leva direto
  pras Configurações.
- Detalhe técnico: os QR codes são desenhados no próprio navegador, então não
  precisei instalar nada novo no servidor (a subida no Coolify continua igual).
- Conferi tudo abrindo as telas de verdade (inclusive o modo de impressão) e os
  testes seguem passando: **329 ok**.

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
- Sistema de cobrança (R$ 147 setup + R$ 3,97/mesa aberta) com faturas mensais
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
