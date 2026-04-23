# MVP - Garcom no WhatsApp para Restaurantes

## Resumo da ideia

Este documento resume a conversa e transforma a ideia em um plano pratico para iniciar o MVP.

O produto nao e um cardapio digital. A maioria dos sistemas atuais faz o cliente mandar mensagem no WhatsApp e receber um link para abrir cardapio, navegar, montar carrinho e finalizar pedido.

A proposta aqui e diferente:

> O cliente ja esta sentado no restaurante, ja viu o cardapio fisico na mesa, e quer apenas pedir algo simples sem ficar chamando garcom.

O cliente escaneia um QR Code da mesa, abre o WhatsApp e fala ou digita naturalmente:

> "Me ve 2 Corona e uma porcao de batata."

O bot entende, confirma e envia o pedido para o painel correto:

- Bar/balcao: 2 Corona
- Cozinha: 1 porcao de batata

O objetivo e colocar um "garcom invisivel" dentro do WhatsApp, sem obrigar o cliente a baixar app, criar conta ou navegar em cardapio digital.

## Frase central do produto

> O cliente pede por audio ou texto no WhatsApp. O pedido cai limpo no balcao, cozinha ou painel do garcom.

Outras frases comerciais:

- "Peca outra bebida sem levantar a mao."
- "Sem app, sem cardapio digital, sem esperar garcom."
- "O garcom fica na palma da mao do cliente."
- "Seu cliente fala no WhatsApp como falaria com um garcom."
- "Aumente o consumo por mesa reduzindo o atrito do re-pedido."

## Diferencial contra concorrentes

Concorrentes comuns:

- Cardapio digital com link
- QR Code que abre menu web
- Pedido via carrinho
- Cliente precisa navegar, escolher, montar e finalizar

Este produto:

- Usa o cardapio fisico que ja esta na mesa
- Cliente pede por audio ou texto
- IA entende linguagem natural
- Bot confirma o pedido
- Pedido vai direto para cozinha, bar, salao ou caixa
- Garcom nao precisa anotar itens simples
- Cliente nao precisa gritar "garcom"

O diferencial real nao e "ter IA". O diferencial e:

> Reduzir o tempo entre a vontade do cliente e o pedido chegar na operacao.

## Contexto do projeto atual

O projeto atual `antigravit-politica` ja tem a base tecnica para isso.

Fluxo existente:

- `server.py` recebe mensagens WhatsApp via Evolution API no endpoint `/webhook`.
- O sistema processa texto e audio.
- Audio pode ser transcrito com OpenAI Whisper.
- Mensagens de um numero autorizado sao roteadas para `gabinete_agent.py`.
- `gabinete_agent.py` usa OpenAI function calling.
- O agente tem a ferramenta `criar_tarefa`.
- A ferramenta grava em `tarefas_gabinete`.
- O painel lista tarefas pela rota `/api/tarefas`.
- A UI mostra as tarefas no dashboard.

Traducao para restaurante:

- `criar_tarefa` vira `criar_pedido`.
- `tarefas_gabinete` vira `pedidos` e `pedido_itens`.
- "responsavel" vira setor: bar, cozinha, salao ou caixa.
- "deadline" vira tempo estimado ou SLA.
- "status" vira fluxo operacional do pedido.

## Fluxo ideal do MVP

1. Garcom chega na mesa e explica:
   "Pessoal, se quiserem pedir bebida, porcao ou chamar atendimento, escaneiem esse QR e mandem audio ou texto no WhatsApp. O pedido cai direto no nosso sistema."

2. Cliente escaneia o QR Code da mesa.

3. WhatsApp abre com uma mensagem pre-preenchida:
   "Mesa 12"

4. Cliente envia a primeira mensagem.

5. Sistema cria ou ativa uma sessao da mesa.

6. Bot responde:
   "Mesa 12 liberada. Pode pedir por audio ou texto."

7. Cliente manda:
   "Me ve 2 Corona e uma porcao de batata."

8. IA interpreta:
   - 2x Corona
   - 1x Porcao de batata
   - Mesa 12
   - Setor bar para Corona
   - Setor cozinha para batata

9. Bot responde:
   "Perfeito. Mesa 12: 2 Corona e 1 porcao de batata. Confirma?
   1 - Confirmar
   2 - Alterar"

10. Cliente responde:
   "1"

11. Sistema cria o pedido confirmado.

12. Pedido aparece no painel:
   - Bar: 2 Corona
   - Cozinha: 1 porcao de batata

13. Bot responde:
   "Pedido confirmado. Ja mandei para o balcao e cozinha."

## Casos de uso principais

### Pedido simples

Cliente:

> Me ve 2 Corona e uma batata.

Bot:

> Perfeito. Mesa 12: 2 Corona e 1 porcao de batata. Confirma?
> 1 - Confirmar
> 2 - Alterar

Cliente:

> 1

Bot:

> Pedido confirmado. Ja mandei para o balcao e cozinha.

### Pedido incompleto

Cliente:

> Manda uma Brahma.

Bot:

> Brahma lata ou 600ml?

Cliente:

> 600

Bot:

> Fechado. Mesa 12: 1 Brahma 600ml. Confirma?
> 1 - Confirmar
> 2 - Alterar

### Pedido fora do cardapio

Cliente:

> Quero uma cerveja que voces nao tem no cardapio.

Bot:

> Nao encontrei esse item no cardapio da casa. Posso chamar um atendente para ajudar?

### Pedido de atendimento

Cliente:

> Traz mais guardanapo e limao.

Bot:

> Combinado. Chamei o atendimento da Mesa 12 para levar guardanapo e limao.

Painel:

- Setor: salao
- Mesa: 12
- Solicitacao: guardanapo e limao

### Fechar conta

Cliente:

> Fecha a conta.

Bot:

> Ja pedi o fechamento da Mesa 12. Um atendente vai levar a conta.

Painel:

- Setor: caixa/salao
- Mesa: 12
- Acao: fechar conta

### Repetir pedido

Cliente:

> Manda outra rodada igual.

Bot consulta o ultimo pedido de bebidas da mesa e responde:

> Outra rodada: 2 Corona. Confirma?
> 1 - Confirmar
> 2 - Alterar

## Regras de produto

1. Nada vai para cozinha ou bar sem confirmacao do cliente.
2. O bot nunca inventa item fora do cardapio.
3. Se houver duvida, pergunta de forma curta.
4. Se nao conseguir resolver, chama humano.
5. Pedido confirmado nao deve ser duplicado se o webhook repetir evento.
6. Audio deve ter limite de duracao no MVP, por exemplo 35 segundos.
7. O cliente deve poder pedir por texto ou audio.
8. O cardapio e interno para a IA entender pedidos, nao precisa ser mostrado ao cliente.
9. A mesa precisa estar ativa para aceitar pedidos.
10. Quando a conta fecha, a sessao da mesa expira.

## Protecao contra pedidos falsos

QR Code estatico sozinho nao prova que a pessoa esta no restaurante. Se alguem fotografa o QR da mesa, pode tentar pedir de fora.

A solucao recomendada e usar camadas de seguranca.

### Fluxo seguro recomendado

1. Garcom abre ou valida a mesa no painel.
2. Cliente escaneia QR Code.
3. Sistema cria sessao pendente.
4. Primeiro pedido fica como `aguardando_validacao_mesa`.
5. Painel mostra:
   "Novo check-in na Mesa 12".
6. Garcom valida visualmente que existe cliente naquela mesa.
7. Depois disso, aquele WhatsApp fica vinculado a mesa.
8. Novos pedidos entram direto ate a conta ser fechada.

### Estados da mesa

- `mesa_livre`
- `mesa_ocupada`
- `sessao_pendente`
- `sessao_ativa`
- `conta_solicitada`
- `sessao_fechada`

### Estados do pedido

- `rascunho`
- `aguardando_confirmacao_cliente`
- `aguardando_validacao_mesa`
- `enviado_setor`
- `em_preparo`
- `pronto`
- `entregue`
- `cancelado`

### Camadas de defesa

- QR Code aponta para o sistema, nao direto para `wa.me`.
- Token do QR deve ser seguro, aleatorio e revogavel.
- Mesa precisa estar aberta para aceitar pedido.
- Primeiro pedido da mesa exige validacao humana.
- Sessao fica travada no WhatsApp do cliente validado.
- Segundo numero tentando pedir na mesma mesa exige aprovacao.
- Sessao expira ao fechar a conta.
- Bloqueio de comportamento suspeito:
  - muitas mensagens em poucos segundos
  - mesmo numero tentando varias mesas
  - mesa livre recebendo pedido
  - restaurante fechado
  - pedido muito caro na primeira interacao
  - muitas tentativas canceladas

## Arquitetura recomendada para projeto novo

Criar um projeto novo, em vez de copiar o monolito inteiro.

Sugestao de modulos:

- `server.py` ou `app.py`
  - App Flask/FastAPI principal
  - rotas de webhook
  - rotas de painel

- `whatsapp_adapter.py`
  - enviar mensagem
  - receber webhook
  - baixar audio
  - normalizar payload da Evolution API ou WhatsApp Cloud API

- `audio_service.py`
  - transcrever audio com OpenAI
  - validar tamanho e formato

- `restaurant_agent.py`
  - prompt principal do garcom digital
  - function calling
  - decisao de ferramenta

- `menu_service.py`
  - consultar produtos
  - buscar aliases
  - verificar disponibilidade
  - resolver nomes parecidos

- `order_service.py`
  - criar rascunho de pedido
  - confirmar pedido
  - dividir pedido por setor
  - atualizar status

- `table_session_service.py`
  - abrir mesa
  - validar sessao
  - vincular WhatsApp a mesa
  - fechar sessao

- `qr_service.py`
  - gerar QR por mesa
  - criar token seguro
  - expirar/revogar token

- `dashboard`
  - painel do bar
  - painel da cozinha
  - painel do salao
  - painel do caixa

## Banco de dados sugerido

### `restaurantes`

- `id`
- `nome`
- `slug`
- `telefone_whatsapp`
- `timezone`
- `ativo`
- `criado_em`

### `unidades`

- `id`
- `restaurante_id`
- `nome`
- `endereco`
- `cidade`
- `ativo`

### `mesas`

- `id`
- `restaurante_id`
- `unidade_id`
- `numero`
- `nome`
- `status`
- `qr_token_atual`
- `ativa`

### `sessoes_mesa`

- `id`
- `restaurante_id`
- `unidade_id`
- `mesa_id`
- `cliente_whatsapp`
- `status`
- `aberta_por_funcionario_id`
- `validada_por_funcionario_id`
- `aberta_em`
- `validada_em`
- `fechada_em`

### `produtos`

- `id`
- `restaurante_id`
- `nome`
- `descricao`
- `preco`
- `categoria`
- `setor`
- `ativo`
- `disponivel`

Setores:

- `bar`
- `cozinha`
- `salao`
- `caixa`

### `produto_aliases`

- `id`
- `produto_id`
- `alias`

Exemplos:

- Produto: "Porcao de batata frita"
- Aliases: "batata", "fritas", "batata frita", "porcao de batata"

### `pedidos`

- `id`
- `restaurante_id`
- `unidade_id`
- `mesa_id`
- `sessao_mesa_id`
- `cliente_whatsapp`
- `status`
- `total_estimado`
- `texto_original`
- `origem`
- `criado_em`
- `confirmado_em`

### `pedido_itens`

- `id`
- `pedido_id`
- `produto_id`
- `nome_snapshot`
- `quantidade`
- `preco_unitario_snapshot`
- `setor`
- `observacoes`
- `status`

### `solicitacoes_salao`

- `id`
- `restaurante_id`
- `mesa_id`
- `sessao_mesa_id`
- `tipo`
- `descricao`
- `status`
- `criada_em`
- `concluida_em`

Tipos:

- `chamar_garcom`
- `guardanapo`
- `talher`
- `molho`
- `limpeza`
- `fechar_conta`
- `outro`

### `mensagens_whatsapp`

- `id`
- `restaurante_id`
- `message_id`
- `remote_jid`
- `mesa_id`
- `sessao_mesa_id`
- `tipo`
- `texto`
- `audio_url`
- `payload_bruto`
- `processada`
- `criada_em`

Usar `message_id` para idempotencia e evitar pedido duplicado.

### `eventos_pedido`

- `id`
- `pedido_id`
- `tipo`
- `descricao`
- `criado_por`
- `criado_em`

## Ferramentas do agente

O agente deve ter poucas ferramentas, mas bem definidas.

### `consultar_cardapio`

Entrada:

- texto do cliente
- restaurante_id

Saida:

- itens candidatos
- produtos encontrados
- produtos ambiguos
- produtos indisponiveis

### `criar_rascunho_pedido`

Cria um pedido ainda nao enviado para producao.

Entrada:

- mesa_id
- sessao_mesa_id
- itens
- texto_original

Saida:

- pedido_id
- resumo
- total_estimado
- pendencias

### `confirmar_pedido`

Confirma pedido e envia itens para setores.

Entrada:

- pedido_id

Saida:

- pedido confirmado
- setores acionados

### `criar_solicitacao_salao`

Para pedidos que nao sao comida/bebida:

- chamar garcom
- trazer guardanapo
- trazer limao
- limpar mesa
- fechar conta

### `consultar_ultimo_pedido`

Para comandos como:

- "manda outra"
- "repete a rodada"
- "mais uma igual"

### `chamar_humano`

Quando a IA nao conseguir resolver com seguranca.

## Prompt base do agente

Objetivo:

Voce e o garcom digital do restaurante. O cliente esta sentado em uma mesa e pode pedir por audio ou texto no WhatsApp. Sua funcao e transformar pedidos naturais em pedidos estruturados para o bar, cozinha, salao ou caixa.

Regras:

- Responda curto e natural.
- Nunca invente item fora do cardapio.
- Nunca envie pedido para producao sem confirmacao.
- Se o pedido estiver claro, monte o resumo e peca confirmacao.
- Se houver duvida, faca uma pergunta curta.
- Se for pedido de atendimento, crie solicitacao para o salao.
- Se o cliente pedir conta, crie solicitacao para caixa/salao.
- Se o cliente responder "1", "sim", "confirma", "pode mandar", confirme o pedido pendente.
- Se o cliente responder "2", "alterar", "mudar", pergunte o que deseja alterar.
- Nao use linguagem tecnica.
- Nunca fale que e IA.
- Use o nome da mesa quando necessario.

Formato de confirmacao:

Mesa {numero}: {itens}. Confirma?
1 - Confirmar
2 - Alterar

Formato depois de confirmar:

Pedido confirmado. Ja mandei para {setores}.

## Painel do MVP

O painel inicial deve ter quatro abas ou colunas:

### Bar

Itens de bebida:

- cerveja
- whisky
- drinks
- refrigerante
- agua

### Cozinha

Itens de comida:

- porcoes
- pratos
- lanches
- sobremesas

### Salao

Solicitacoes:

- chamar garcom
- guardanapo
- talher
- molho
- limpeza
- outros

### Caixa

Solicitacoes:

- fechar conta
- pagamento
- dividir conta

Cada card deve mostrar:

- mesa
- horario
- item ou solicitacao
- observacoes
- status
- botoes:
  - iniciar
  - pronto
  - entregue
  - cancelar

## Status por setor

Para cada item:

- `novo`
- `em_preparo`
- `pronto`
- `entregue`
- `cancelado`

Para solicitacao de salao:

- `nova`
- `em_atendimento`
- `concluida`
- `cancelada`

## MVP em etapas

### Etapa 1 - Base funcional

- Criar projeto novo
- Configurar Flask/FastAPI
- Configurar Supabase
- Criar tabelas principais
- Criar painel simples
- Cadastrar restaurante, mesas e produtos

### Etapa 2 - WhatsApp

- Receber webhook da Evolution API
- Enviar mensagem pelo WhatsApp
- Identificar mesa pelo QR/mensagem inicial
- Salvar mensagens recebidas
- Implementar idempotencia por `message_id`

### Etapa 3 - Audio

- Baixar audio da Evolution API
- Transcrever com OpenAI Whisper ou modelo equivalente
- Processar texto transcrito como pedido

### Etapa 4 - Agente

- Criar `restaurant_agent.py`
- Definir prompt do garcom digital
- Definir ferramentas
- Extrair itens do pedido
- Criar rascunho
- Pedir confirmacao
- Confirmar pedido

### Etapa 5 - Painel operacional

- Mostrar pedidos por setor
- Atualizar status
- Tocar alerta visual/sonoro para novo pedido
- Botao para humano assumir conversa

### Etapa 6 - Seguranca de mesa

- Mesa precisa estar ativa
- Primeiro pedido precisa validacao
- Sessao vinculada ao WhatsApp
- Fechar conta encerra sessao

## Canais para Brasil e Londres

### Brasil

Comecar com WhatsApp.

Motivo:

- Uso massivo
- Cliente ja esta acostumado
- Restaurantes ja atendem pelo WhatsApp

### Londres/Reino Unido

Comecar com:

1. WhatsApp
2. Telegram
3. Web fallback pelo QR

Motivo:

- WhatsApp e o app de mensagens mais comum no Reino Unido.
- Telegram tem API de bot excelente e pode ser diferencial.
- O fallback web evita perder clientes que nao querem usar WhatsApp.

Produto para Londres:

> Cliente fala em ingles, portugues ou espanhol. Painel recebe o pedido estruturado no idioma do restaurante.

Exemplos:

Cliente:

> Can I get two Coronas and fries?

Painel:

> Table 12: 2 Corona, 1 fries

Cliente brasileiro em Londres:

> Me ve uma caipirinha e uma picanha.

Painel:

> Mesa 8: 1 caipirinha, 1 picanha

## Mercado pesquisado

### Brasil

Existem muitas solucoes de cardapio digital e pedidos pelo WhatsApp:

- Anota AI
- Goomer
- Saipos
- ComidAI
- VamoPedir
- Garcom Digital
- RapidFood
- CardZap
- PedidoWhats
- ClickPede

Leitura:

O mercado brasileiro esta cheio de cardapio digital. Entrar como "mais um cardapio digital" nao e o melhor caminho.

Melhor posicionamento:

> Pedido por voz/texto no WhatsApp direto da mesa, sem cardapio digital.

### Reino Unido / Londres

Concorrente mais parecido encontrado:

- WPOrder
  - WhatsApp + Telegram
  - IA
  - dashboard
  - construido em Londres
  - foco em takeaways

Outras solucoes do Reino Unido:

- Wetherspoon App
- SumUp Order & Pay
- Posso
- YouPos
- Kobas
- QR/order-at-table apps

Leitura:

No Reino Unido ja existe validacao de mercado para pedidos por mesa e pedido conversacional. A oportunidade e focar em restaurantes independentes, bares, pubs, restaurantes brasileiros, portugueses, latinos, indianos, turcos e pequenos cafes.

## Tese de negocio

O dinheiro nao esta apenas no primeiro pedido. O dinheiro esta no re-pedido:

- mais uma cerveja
- outra rodada
- uma porcao extra
- mais gelo
- mais guardanapo
- fechar conta mais rapido

O cliente muitas vezes consumiria mais, mas desiste porque o garcom demora.

Tese:

> Aumentar consumo por mesa reduzindo atrito no re-pedido.

## Publico inicial ideal

### Brasil

- bares cheios
- botecos
- choperias
- hamburguerias
- espetinhos
- restaurantes com area externa
- beach clubs
- rooftops
- casas noturnas com mesas

### Londres

- restaurantes brasileiros
- restaurantes portugueses
- bares latinos
- takeaways independentes
- pubs pequenos
- restaurantes de imigrantes
- cafes com pouco staff

## Modelo de cobranca inicial

MVP/piloto:

- mensalidade fixa por unidade
- sem comissao por pedido

Exemplo Brasil:

- R$ 199/mes para piloto
- R$ 299 a R$ 499/mes depois, dependendo do volume

Exemplo Reino Unido:

- 39 a 79 GBP/mes para restaurantes pequenos
- planos maiores para multi-unidade

Argumento:

> Sem comissao. O restaurante paga mensalidade e fica com toda a margem.

## Integracoes futuras

Depois do MVP:

- PDV
- impressora termica
- KDS
- Pix
- Stripe
- Mercado Pago
- Apple Pay / Google Pay no Reino Unido
- WhatsApp Cloud API oficial
- Telegram Bot
- Apple Messages for Business
- relatorios de ticket medio
- tempo medio de preparo
- ranking de itens mais pedidos
- upsell automatico
- programa de fidelidade

## O que NAO fazer no MVP

- Nao construir cardapio digital completo.
- Nao construir aplicativo mobile.
- Nao integrar PDV no primeiro momento.
- Nao criar marketplace.
- Nao implementar pagamento complexo antes de validar pedido por mesa.
- Nao deixar IA confirmar pedido sem cliente.
- Nao depender de geolocalizacao como seguranca principal.

## Proxima conversa - prompt recomendado

Use este texto para iniciar a proxima conversa:

```text
Quero construir o MVP do produto descrito no arquivo MVP_GARCOM_WHATSAPP.md.

O produto e um garcom por WhatsApp para restaurantes. Nao e cardapio digital.

Fluxo principal:
1. Cliente escaneia QR da mesa.
2. Abre WhatsApp com identificacao da mesa.
3. Cliente manda audio ou texto com pedido.
4. Sistema transcreve se for audio.
5. IA entende itens do cardapio interno.
6. Bot pede confirmacao.
7. Cliente confirma com "1".
8. Pedido vai para painel por setor: bar, cozinha, salao ou caixa.

Quero comecar pelo MVP tecnico usando Flask, Supabase, Evolution API e OpenAI, reaproveitando a logica do projeto atual onde WhatsApp cria tarefas no painel.

Antes de programar, leia o arquivo MVP_GARCOM_WHATSAPP.md e monte o plano de implementacao em etapas. Depois implemente a primeira etapa.
```

## Nome interno sugerido

Opcoes:

- MesaZap
- ZapGarcom
- Garcom de Bolso
- ComandaZap
- MesaFala
- WaiterZap
- WhatsWaiter

Nome interno recomendado para o MVP:

> MesaZap

Motivo:

- Simples
- Brasileiro
- Entende rapido
- Tem ligacao direta com mesa + WhatsApp

