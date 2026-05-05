# Plano de Cold Outreach - MesaZap

## Objetivo

Construir uma maquina de prospeccao automatica para vender o MesaZap (garcom no WhatsApp)
para bares e restaurantes onde o atrito de chamar garcom e maior:

- bares de praia, beach clubs, quiosques
- rooftops e bares com area externa grande
- choperias, hamburguerias, espetarias com salao cheio
- pubs, casas noturnas com mesas
- restaurantes em shopping com mesas distantes do balcao

A pipeline deve:

1. Encontrar lugares com alto movimento e layout disperso.
2. Coletar telefone e email do estabelecimento.
3. Enviar cold email pelo agente de email.
4. Enviar cold message pelo agente de WhatsApp.
5. Conversar, qualificar e agendar uma call com o dono.
6. Devolver o lead "quente" para um humano fechar.

## Tese de prospeccao

> Quanto maior a distancia media entre cliente e garcom, maior a dor.
> Bar de praia perde re-pedido toda vez que o cliente nao quer levantar.
> O MesaZap converte essa friccao em receita.

Esse e o gancho central de todo o cold outreach. O argumento muda
dependendo do tipo de casa (praia, rooftop, boteco, hamburgueria), mas
o nucleo e sempre o mesmo: "voces estao perdendo re-pedido".

## Aviso legal e de risco - leia antes de codar

Esta automacao toca tres areas sensiveis. Ignorar isso da multa, ban e
queima de dominio/numero.

### LGPD (Brasil) e GDPR (UK/UE)

- Email B2B para `contato@restaurante.com` e legitimo interesse, mas
  precisa de opt-out em todo email e canal de revogacao.
- Manter base de supressao (quem pediu para nao receber nunca mais).
- Nao usar email pessoal de funcionario (`joao.silva@gmail.com`) raspado.
- Guardar evidencia da fonte publica do dado (ex.: Google Maps).
- Politica de privacidade publica no dominio do remetente.

### WhatsApp ToS

- WhatsApp pessoal nao foi feito para outbound em massa. Vai banir.
- Estrategia segura: WhatsApp Business API (Cloud API) com template
  aprovado para o primeiro contato, depois conversa livre na janela
  de 24h.
- Alternativa de bootstrap: 2 a 3 chips Business com Evolution API,
  warmup, volume baixo, mensagens humanizadas, opt-out claro. Aceitar
  que esses chips sao descartaveis.
- Nunca usar o mesmo numero do produto (MesaZap) para outbound frio.
  Outbound queima numero. Manter numero do produto limpo.

### Anti-spam de email

- Dominio separado do dominio principal (ex.: `mesazap.com.br` fica
  limpo, outbound usa `getmesazap.com`, `mesazap.app`, `trymesazap.com`).
- SPF, DKIM, DMARC configurados.
- Warmup de 2 a 4 semanas antes de volume.
- Limite por caixa: 30 a 50 emails/dia no comeco.
- Multiplas caixas e multiplos dominios para escalar (ex.: 3 dominios x
  3 caixas x 40 emails = 360/dia).
- Opt-out em todo email.

## Arquitetura geral

```
[Discovery]      -> [Enrichment]    -> [Qualification] -> [CRM]
 Google Places       Email finder       Filtros e score    Supabase
 Google Maps         Site scrape        Heuristicas        leads
 Instagram           Whois              IA classifica
                                                          |
                                                          v
                                          [Email Agent] [WhatsApp Agent]
                                          warmup        Evolution API
                                          Resend/SES    template + conversa
                                                          |
                                                          v
                                                    [Booking Agent]
                                                    Google Calendar
                                                    Cal.com link
                                                          |
                                                          v
                                                    [Hand-off humano]
```

Modulos novos sugeridos no projeto:

- `outreach/discovery_service.py` - busca Google Places.
- `outreach/enrichment_service.py` - acha email e telefone.
- `outreach/qualification_service.py` - score e filtro.
- `outreach/email_agent.py` - agente de cold email.
- `outreach/whatsapp_outbound_agent.py` - agente de cold WhatsApp.
- `outreach/booking_agent.py` - agendamento.
- `outreach/sender_email.py` - envio via Resend/SES/SMTP.
- `outreach/sender_whatsapp.py` - envio via Evolution.
- `outreach/dashboard/` - paineis de pipeline.

Manter completamente separado do produto MesaZap:

- Banco compartilhado (Supabase), schema diferente: `outreach_*`.
- Numero WhatsApp diferente do produto.
- Dominio de email diferente do dominio principal.

## Pipeline em 7 camadas

### Camada 1 - Discovery (encontrar lugares)

Fonte primaria recomendada: **Google Places API (New) / Text Search**.

Por que nao raspar Google Maps direto:

- ToS proibe scraping.
- Captcha e rate limit derrubam o robo.
- Places API custa pouco (~$32/1000 buscas Text Search) e e legal.

Estrategia de query:

```
"bar de praia em <cidade>"
"beach club <cidade>"
"choperia <bairro>"
"hamburgueria com area externa <cidade>"
"rooftop bar <cidade>"
"restaurante na praia <cidade>"
"quiosque <praia>"
```

Para cada lugar, salvar:

- `place_id`, `nome`, `endereco`, `lat`, `lng`
- `rating`, `total_reviews` (proxy de movimento)
- `price_level`
- `tipos` (bar, restaurant, night_club)
- `telefone` (formattedPhoneNumber)
- `website`
- `horario_funcionamento`
- `foto_principal_url`

Heuristica de "movimento":

- `total_reviews >= 200` (filtro forte)
- `rating >= 4.0`
- tipo contem `bar`, `night_club`, `meal_takeaway` ou nome contem
  "praia", "beach", "rooftop", "boteco", "choperia"
- aberto a noite (horario funcionamento)

Saida: tabela `outreach_leads` com status `descoberto`.

### Camada 2 - Enrichment (achar email)

Places API nao retorna email. Estrategias em cascata:

1. **Scrape do website** retornado pelo Places. Procurar `mailto:`,
   `contato`, `reservas`, `parcerias` em paginas comuns:
   `/`, `/contato`, `/reservas`, `/sobre`, `/parceiros`.
2. **Instagram bio** (se disponivel). Bio costuma ter email.
3. **Hunter.io / Apollo / Snov.io** como API paga para email finder
   por dominio. Custo: ~$0.05 a $0.20 por email.
4. **Padroes comuns** a partir do dominio:
   `contato@`, `atendimento@`, `reservas@`, `comercial@`, `parcerias@`.
   Validar com SMTP check (Hunter, NeverBounce).

Ordem de preferencia de destinatario:
`parcerias > comercial > reservas > contato > atendimento`.

Para telefone: Places ja entrega. Normalizar para E.164 (+55...).

Saida: `outreach_leads.email`, `outreach_leads.telefone_e164`,
`outreach_leads.email_confidence` (high/medium/low).

### Camada 3 - Qualification (filtrar e priorizar)

Antes de gastar email/whats, classificar:

- `score_movimento` = funcao de reviews, rating, price_level.
- `score_layout` = palavras no nome/descricao/site:
  "praia", "beach", "rooftop", "area externa", "deck", "jardim",
  "varanda", "salao", "espacoso", "ao ar livre".
- `score_dor` = score_movimento * score_layout.

Usar IA (gpt-4o-mini ou Haiku) para classificar a partir do site +
reviews top 5: "este lugar provavelmente tem mesas longe do bar?
Sim/Nao + justificativa".

Filtrar:

- score_dor > threshold
- tem email ou telefone
- nao esta na supressao
- nao foi contatado nos ultimos 90 dias

Saida: `outreach_leads.status = qualificado`, `priority = 1..5`.

### Camada 4 - Cold Email (agente 1)

Sequencia de 4 toques em 14 dias:

| Dia | Toque        | Objetivo                          |
| --- | ------------ | --------------------------------- |
| 0   | E1 - intro   | gancho da dor + 1 frase de prova  |
| 3   | E2 - prova   | mini case ou numero               |
| 7   | E3 - quebra  | "talvez nao seja para voces"      |
| 14  | E4 - bump    | reply curto, 1 linha              |

Regras:

- Assunto curto, minusculo, parece email pessoal.
- Sem imagens, sem HTML pesado, sem trackers visiveis.
- Texto plano com 1 link (Cal.com) e assinatura simples.
- Personalizacao real: nome do bar, cidade, algo do site/reviews.
- Sempre opt-out em uma linha no rodape.

Exemplo E1 (template, agente preenche):

```
Assunto: pedido na mesa do {bar}

oi {primeiro_nome_dono ou "pessoal do {bar}"},

passei pelo site de voces e vi que tem {detalhe_real_do_lugar}.
em casa cheia, cliente longe do balcao desiste do segundo pedido.

a gente fez um garcom no whatsapp: cliente escaneia o qr da mesa,
fala "me ve mais 2 corona" e o pedido cai no bar e cozinha. sem
app, sem cardapio digital.

faz sentido eu te mandar um video de 90s de como funciona?

{nome}
{telefone}

---
se nao for o canal certo, me avisa e tiro da lista.
```

Ferramentas do agente de email:

- `gerar_email(lead_id, toque_n)` - gera personalizado.
- `enviar_email(lead_id, toque_n)` - envia via Resend/SES.
- `registrar_resposta(lead_id, payload)` - chamado pelo webhook.
- `classificar_resposta(texto)` - interessado / negativa / oof /
  pergunta / opt-out.
- `agendar_call(lead_id, slot)` - cria evento Calendar.
- `pausar_sequencia(lead_id, motivo)`.
- `mover_para_supressao(lead_id)`.

Stack de envio recomendada:

- **Resend** (Brasil/UK, simples, bom deliverability) ou **AWS SES**
  (mais barato em escala). Postmark e otimo para transacional, evitar
  para cold.
- Webhook de inbound: **Resend Inbound** ou **Cloudflare Email Routing
  + Worker** ou Postmark Inbound apontando para `/webhook/email_in`.

### Camada 5 - Cold WhatsApp (agente 2)

Estrategia mais conservadora porque numero queima.

Tres modos possiveis:

#### Modo A - Cloud API oficial (recomendado para escala)

- Cadastra Business Manager.
- Cria template de marketing aprovado:
  ```
  oi {{1}}, vi que voces tem {{2}}. fizemos um garcom no whatsapp
  pra reduzir o tempo de re-pedido em mesa cheia. posso te mandar
  um video de 90s? -- responda PARAR para nao receber.
  ```
- Custa por conversa (Brasil ~R$0,30-0,80 marketing).
- Nao queima numero, mas exige aprovacao de template.

#### Modo B - Evolution API com chip Business (bootstrap)

- 2 a 3 chips dedicados, separados do produto.
- Warmup: 7 dias trocando mensagens entre chips e contatos amigos.
- Volume: 20 a 40 mensagens novas/dia/chip no comeco.
- Intervalo aleatorio 40 a 180s entre envios.
- Salvar contato antes de enviar (reduz risco).
- Sempre incluir "responda SAIR" no primeiro toque.
- Aceitar que chip pode banir e ter chip reserva.

#### Modo C - hibrido

- Cloud API para o primeiro toque (template).
- Evolution para conversa apos o lead responder (mais barato e flexivel
  na janela de 24h).

Sequencia:

| Dia | Toque                                          |
| --- | ---------------------------------------------- |
| 0   | template oficial curto + link de video         |
| 2   | follow-up se nao respondeu (so se Cloud API)   |
| 5   | ultimo toque com oferta de teste gratis 14d    |

Quando o lead responder, conversa vai para o agente de conversa
(camada 6).

Ferramentas do agente WhatsApp outbound:

- `enviar_template(lead_id, template_id, params)`
- `enviar_mensagem_livre(lead_id, texto)` (so se janela aberta)
- `classificar_intencao(texto)` -> interessado, duvida, negativa,
  opt-out, fora do horario, pessoa errada.
- `agendar_call(lead_id, slot)`
- `escalar_para_humano(lead_id, motivo)`
- `pausar_lead(lead_id, ate_quando)`

### Camada 6 - Conversacao + agendamento

Quando o lead responde (email ou whats), entra um agente de conversa
unico (mesma logica, dois canais). Objetivo: marcar call de 15 min.

Prompt base:

> Voce e SDR do MesaZap. Sua unica meta e agendar uma call de 15
> minutos com o dono ou gerente. Nao venda no chat. Responda curto,
> humano, sem emoji em excesso. Se a pessoa pedir mais info, mande
> 2 frases e ofereca a call. Se a pessoa nao for decisora, peca o
> contato de quem decide. Se nao for o momento, agende um lembrete
> futuro. Se for opt-out, encerre com agradecimento.

Regras duras:

- Nunca diga que e IA.
- Nunca prometa preco fechado.
- Nunca confirme integracao especifica sem checagem humana.
- Apos 3 trocas sem avanco, escalar humano.

Ferramentas:

- `consultar_lead(lead_id)` - contexto do lead.
- `propor_horarios(lead_id)` - retorna 3 slots livres do Calendar.
- `agendar_call(lead_id, slot, contato)` - cria evento + envia convite.
- `enviar_video_demo(lead_id)` - link curto.
- `escalar_humano(lead_id, motivo)` - notifica Slack/email do dono.
- `marcar_nao_interessado(lead_id, motivo)`.
- `pausar_para(lead_id, data)` - "me chama em 2 meses".

Booking:

- Cal.com publico para auto-agendamento (`/cal/mesazap/15min`).
- Para agendamento direto pelo agente: Google Calendar API com
  `freebusy.query` e `events.insert`.

### Camada 7 - CRM, pipeline e metricas

Pipeline de status do lead:

```
descoberto -> enriquecido -> qualificado -> contatado_email
  -> respondeu -> conversa_ativa -> call_agendada
  -> call_realizada -> proposta -> ganho/perdido
```

Tambem em paralelo:

```
descoberto -> ... -> contatado_whats -> ...
```

Painel deve mostrar:

- Funil por canal (email vs whats).
- Taxa de resposta, taxa de call, taxa de fechamento.
- Caixas de email e chips com saude (% bounce, % spam, ban).
- Leads aguardando humano (escalados).
- Calendar de calls agendadas.

Metricas-alvo iniciais:

- email cold B2B BR: 30-50% open, 5-10% reply, 1-3% call.
- whats cold BR: 60-80% read, 10-20% reply, 3-7% call.
- meta: 20 calls agendadas/semana com 1 caixa + 2 chips.

## Modelo de dados (Supabase)

Schema `outreach_*`. Nao mexe nas tabelas do produto MesaZap.

### `outreach_leads`

- `id`
- `place_id` (Google)
- `nome`
- `tipo` (bar, restaurante, beach_club, rooftop, ...)
- `endereco`, `cidade`, `estado`, `pais`
- `lat`, `lng`
- `rating`, `total_reviews`, `price_level`
- `telefone_e164`
- `email`, `email_confidence`
- `instagram`, `website`
- `score_movimento`, `score_layout`, `score_dor`
- `prioridade` (1-5)
- `status` (descoberto, enriquecido, qualificado, contatado, respondeu,
  call_agendada, ganho, perdido, supressao)
- `motivo_supressao`
- `dono_responsavel_id` (humano da equipe)
- `criado_em`, `atualizado_em`

### `outreach_campanhas`

- `id`
- `nome` (ex.: "Bares de praia RJ - jan 2026")
- `canal` (email, whats, ambos)
- `template_email_id`, `template_whats_id`
- `ativa`, `criada_em`

### `outreach_sequencias`

- `id`
- `lead_id`, `campanha_id`, `canal`
- `toque_atual`, `proximo_envio_em`
- `status` (ativa, pausada, finalizada, opt_out)

### `outreach_mensagens`

- `id`
- `lead_id`, `sequencia_id`, `canal`
- `direcao` (out, in)
- `toque_n`
- `assunto`, `corpo`
- `provider_message_id`
- `status` (queued, sent, delivered, opened, replied, bounced, failed)
- `criada_em`, `entregue_em`, `aberta_em`, `respondida_em`

### `outreach_caixas_email`

- `id`
- `dominio`, `endereco`, `display_name`
- `provider` (resend, ses, smtp_custom)
- `enviados_hoje`, `limite_diario`
- `warmup_status`, `saude_score`
- `ativa`

### `outreach_chips_whats`

- `id`
- `numero_e164`, `instancia_evolution`
- `tipo` (cloud_api, business_chip)
- `enviados_hoje`, `limite_diario`
- `warmup_status`, `banido`, `banido_em`
- `ativa`

### `outreach_supressao`

- `id`
- `email` ou `telefone_e164` (unico)
- `origem` (opt_out_email, opt_out_whats, bounce_hard, manual)
- `criada_em`

### `outreach_calls`

- `id`
- `lead_id`
- `agendada_para`
- `link_meet`
- `responsavel_id`
- `status` (agendada, realizada, no_show, cancelada)
- `notas`

### `outreach_eventos`

- `id`, `lead_id`, `tipo`, `payload_json`, `criado_em`

Auditoria de tudo: cada toque, resposta, classificacao, escalonamento.

## Prompts de referencia

### Agente de Email

```
Voce e SDR senior do MesaZap. Sua meta unica e marcar call de 15min
com decisor de bar/restaurante.

Produto: garcom no whatsapp. cliente escaneia qr da mesa, fala o
pedido por audio ou texto, pedido cai no painel do bar/cozinha. sem
app, sem cardapio digital. resolve atrito de re-pedido em mesa cheia
e mesa longe do balcao.

Cliente ideal: bar de praia, rooftop, choperia, beach club, lugar
cheio onde garcom demora.

Regras:
- escreva como humano, minusculo, sem floreio.
- 1 gancho real do lugar (use o JSON do lead).
- 1 frase de dor, 1 frase de solucao, 1 cta.
- maximo 90 palavras.
- nunca prometa preco, integracao especifica ou prazo.
- termine sempre com opt-out de 1 linha.
- nao diga que e IA.

Ferramentas:
- consultar_lead, gerar_email, enviar_email, agendar_call,
  pausar_sequencia, mover_para_supressao.
```

### Agente de WhatsApp Outbound

```
Voce faz primeiro contato no whatsapp pelo MesaZap.

Regra de canal:
- primeiro toque so via template aprovado.
- depois que o lead responde, voce esta na janela de 24h e pode
  conversar livre.

Regras de conversa:
- mensagens curtas, 1 ideia por mensagem.
- nunca mais de 2 mensagens seguidas sem o lead responder.
- nao envie audio, nao envie video pesado, mande link curto.
- meta unica: agendar call de 15min ou descobrir que nao serve.
- se a pessoa nao for decisora, peca contato de quem decide.
- se pedir para parar, agradeca e marque opt-out.
- nunca diga que e IA.
- nao discuta preco final no chat. ofereca a call.

Ferramentas:
- enviar_template, enviar_mensagem_livre, classificar_intencao,
  propor_horarios, agendar_call, pausar_lead, escalar_humano,
  marcar_nao_interessado, mover_para_supressao.
```

## Roadmap em fases

### Fase 0 - Fundacao (semana 1)

- Comprar 2 dominios de outreach (ex.: `getmesazap.com`, `trymesazap.com`).
- Configurar SPF, DKIM, DMARC nos dois.
- Criar 2 caixas em cada (`joao@`, `parcerias@`).
- Iniciar warmup automatico (Instantly, Smartlead ou warmup proprio).
- Comprar 2 chips Business para outbound, separados do produto.
- Subir instancia Evolution dedicada para outbound.
- Cadastrar Cal.com com link `/mesazap/15min`.
- Criar schema `outreach_*` no Supabase.

### Fase 1 - Discovery + CRM minimo (semana 2)

- Implementar `discovery_service` com Google Places.
- Implementar `enrichment_service` (scrape site + Hunter como fallback).
- Implementar `qualification_service` com IA classificadora.
- Painel basico: tabela de leads com filtros, status manual.
- Meta: 500 leads qualificados na base.

### Fase 2 - Email outbound (semana 3-4)

- Sequencia de 4 toques.
- Webhook de inbound funcionando.
- Agente de email gerando personalizacao real.
- Classificacao de respostas automatica.
- Escalonamento para humano funcional.
- Meta: 100 emails/dia, primeiras calls agendadas.

### Fase 3 - WhatsApp outbound (semana 5-6)

- Decidir Cloud API vs chip Business (recomendo Cloud API se houver
  Business Manager pronto, senao comecar com 2 chips).
- Aprovar template inicial.
- Sequencia de 3 toques.
- Webhook de resposta integrado ao agente de conversa.
- Meta: 30 mensagens/dia, comparar com canal email.

### Fase 4 - Agente de conversa unificado (semana 7)

- Mesmo agente atende email-in e whats-in.
- Booking automatico via Google Calendar.
- Lembretes 24h e 1h antes da call.
- Hand-off humano em Slack quando o lead esquentar.

### Fase 5 - Otimizacao (semana 8+)

- A/B em assunto, gancho, tipo de prova.
- Segmentar campanhas por tipo (praia, rooftop, hamburgueria).
- Onboarding pos-call: enviar contrato e link de QR de mesa
  automaticamente.
- Feedback loop: lead que virou cliente alimenta scoring.

## Riscos e mitigacoes

| Risco                              | Mitigacao                                       |
| ---------------------------------- | ----------------------------------------------- |
| Numero whats banido                | chips dedicados, volume baixo, opt-out claro    |
| Dominio principal queimado         | dominios outbound separados, warmup, SPF/DKIM   |
| Acusacao de spam / LGPD            | base de supressao, opt-out, fonte publica       |
| Google Places caro em escala       | cache de place_id, refresh trimestral           |
| Email finder errando emails        | SMTP check antes de enviar, marcar bounce       |
| IA inventando detalhe do lead      | so personalizar com dados do JSON, nao alucinar |
| Lead respondendo fora do horario   | filas e horario comercial por timezone do lead  |
| Mistura de numero produto/outbound | numeros e dominios fisicamente separados        |

## Custos estimados (mensal, escala media)

- Google Places: 5000 buscas ~ $160.
- Hunter ou Snov: ~ $50.
- Resend ou SES: ~ $20-50.
- WhatsApp Cloud API: ~ R$300-1500 dependendo do volume.
- 2 dominios + caixas: ~ $30.
- Cal.com: $0 (free tier) ou $15.
- LLM (gpt-4o-mini ou Haiku para classif. e geracao): ~ $30-100.
- Infra (Supabase, Evolution): ja existe.

Total: ~ $500-1000/mes para gerar dezenas de calls qualificadas.

## O que NAO fazer

- Nao raspar Google Maps direto (use Places API).
- Nao usar email pessoal de funcionario raspado.
- Nao mandar cold whats do mesmo numero do produto MesaZap.
- Nao mandar email de cold do dominio principal.
- Nao deixar o agente prometer preco ou integracao especifica.
- Nao mandar audio ou video pesado no primeiro toque.
- Nao seguir conversa apos opt-out, mesmo se a pessoa "voltar atras"
  sem opt-in explicito.
- Nao colocar mais de 1 link por email.
- Nao usar tracking pixel agressivo (queima dominio).

## Proximo passo recomendado

Antes de implementar, decidir:

1. WhatsApp Cloud API (oficial) ou bootstrap com chips Business?
2. Resend, SES ou Smartlead/Instantly para email?
3. Quantos dominios de outbound comprar agora?
4. Quem e o "dono" humano que recebe os leads quentes (vai aparecer
   nas calls)?
5. Cidade/regiao piloto: comecar com 1 (ex.: Rio de Janeiro - bares
   de praia) para calibrar antes de escalar.

Apos essas decisoes, implementar Fase 0 e Fase 1 em paralelo.
