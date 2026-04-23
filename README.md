# MesaZap

MVP de garcom por WhatsApp para restaurantes. O cliente escaneia o QR da mesa, manda texto ou audio no WhatsApp, recebe uma confirmacao curta e o pedido cai no painel certo: bar, cozinha, salao ou caixa.

Esta primeira versao entrega uma base funcional local:

- Flask app com painel operacional.
- Banco SQLite local para desenvolvimento rapido.
- Schema Supabase em `supabase/schema.sql`.
- Adapter de webhook para Evolution API.
- Servico de audio preparado para transcricao com OpenAI.
- Agente com parser local e uso opcional da OpenAI quando `OPENAI_API_KEY` existir.
- Suporte inicial para pedidos em portugues, ingles e espanhol.
- Idempotencia por `message_id`.

## Como rodar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

Abra:

```text
http://localhost:5000
```

## Fluxo de teste no painel

Use o simulador do lado esquerdo:

1. Envie `Mesa 12`.
2. Envie `Me ve 2 Corona e uma porcao de batata`.
3. Envie `1`.

Depois da confirmacao, o bar recebe a Corona e a cozinha recebe a batata.

## Webhook Evolution API

Configure no `.env`:

```env
EVOLUTION_API_URL=https://sua-evolution-api
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=sua-instancia
WHATSAPP_PHONE=55...
```

Endpoint:

```text
POST /webhook/evolution
```

O adapter tenta normalizar payloads comuns da Evolution API:

- `data.key.id`
- `data.key.remoteJid`
- `data.message.conversation`
- `data.message.extendedTextMessage.text`
- `data.message.audioMessage.url`

## Supabase

Execute `supabase/schema.sql` no SQL editor do Supabase ou aplique por migration. O MVP local usa SQLite para facilitar desenvolvimento, mas o schema de producao ja inclui:

- chaves estrangeiras;
- constraints de status;
- `message_id` unico para idempotencia;
- indices para filtros por mesa, sessao, setor, status e datas;
- RLS habilitado para as tabelas.

As policies finais devem ser criadas quando o modelo de usuarios do painel estiver definido.

## OpenAI

Sem `OPENAI_API_KEY`, o MVP usa um parser local simples por aliases do cardapio. Com a chave configurada, `mesazap/openai_interpreter.py` tenta interpretar a mensagem por JSON Schema antes de cair no parser local.
O bot responde em portugues, ingles ou espanhol conforme a mensagem do cliente. O painel continua recebendo os itens no nome operacional cadastrado no cardapio.

Audio usa `OPENAI_TRANSCRIPTION_MODEL` e rejeita audios acima de 35 segundos quando o payload informa duracao.
O servico aceita `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, `webm`, `flac`, `oga`, `ogg`. Arquivos com extensao `.opus` sao tratados como `.ogg` no upload (mesmo container Ogg).

## Testes

```powershell
python -m unittest
```

Para a checagem visual do painel:

```powershell
npm install
npm run test:ui
npm run screenshot
```

O screenshot fica em `output/playwright/dashboard.png`.
