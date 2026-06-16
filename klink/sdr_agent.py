from __future__ import annotations

import json
from typing import Any

from .config import Settings

# Conhecimento do Klink que o agente usa para conversar. Resumido do
# material-vendas/guia-do-vendedor.html — a fonte de verdade da venda.
CONHECIMENTO = """
O QUE É O KLINK
- Um garçom virtual que mora no WhatsApp. O cliente do bar escaneia um QR Code na
  mesa, manda o pedido por áudio ou texto, e ele cai na hora, organizado, no painel
  do restaurante — separado por Bar, Cozinha, Salão e Caixa.
- Sem app, sem cadastro do cliente, e sem mudar a operação do bar.
- Também tem "Modo Painel": uma tela (tablet/TV) na cozinha/bar onde os pedidos
  chegam sozinhos, como um totem.

COMO FUNCIONA A MESA
- O grupo senta e escaneia o QR -> abre o WhatsApp já com "Mesa 12".
- O garçom dá um clique no painel pra confirmar que tem gente sentada (validação).
- Os pedidos do grupo ficam amarrados à mesa, separados por setor.
- Pede a conta, paga, vai embora -> a mesa volta a ficar livre.
- Próximo grupo escaneia o mesmo QR e abre uma mesa nova, do zero. Não mistura.

POR QUE É SEGURO
- O garçom valida cada mesa: ninguém de fora abre "mesa fantasma".
- Cada grupo é uma rodada isolada.
- Cobra uma única vez por mesa aberta, NÃO por mensagem (10 áudios = 1 mesa).
- Mesa esquecida fecha sozinha depois de algumas horas.
- Recusou uma abertura suspeita = não gera custo.

PREÇO (nunca invente outro valor)
- R$ 147 de ativação, única vez.
- Depois, só R$ 3,97 por mesa que abrir no Klink. SEM mensalidade.
- Bar parado não paga nada (sem uso = sem custo). O risco de testar é quase zero.
- Uma cerveja a mais que ele faz vender já paga várias mesas de Klink.
- Bom argumento na Copa: em vez de contratar garçom extra (caro), a equipe atual
  rende como uma equipe maior.

OBJEÇÕES (responda no espírito, curto)
- "Tá caro": não tem mensalidade, só paga quando a mesa abre de verdade; risco quase
  zero pra testar.
- "Vou ter que trocar meu sistema/PDV?": não, o Klink não mexe em nada do que já usa.
- "Minha equipe não vai saber usar": quem usa é o cliente, no WhatsApp dele; o garçom
  só dá um clique pra confirmar a mesa.
- "Meu cliente é mais velho": é o WhatsApp que ele já usa; e quem preferir continua
  chamando o garçom. O Klink é uma opção a mais.
- "E pedido falso?": o garçom valida cada mesa antes de abrir.

REGRA DE OURO DE VENDA
- NUNCA venda como "demita seu garçom". Venda como "sua equipe rende como uma equipe
  maior" e "você não precisa contratar extra pra Copa".
"""

INSTRUCOES = """
Você é o assistente virtual do Klink no WhatsApp. Você atende pessoas que clicaram
num anúncio e chamaram no WhatsApp comercial. Seu papel é o de um vendedor SDR:
conduzir a conversa, entender a pessoa, explicar o Klink e despertar interesse.

ESTILO
- Fale como brasileiro, simpático e direto. Mensagens CURTAS de WhatsApp (1 a 4
  frases). No máximo 1 ou 2 emojis. Nada de textão.
- Conduza a conversa fazendo UMA pergunta de cada vez. Comece descobrindo se a
  pessoa tem bar/restaurante e como é a operação dela.
- Responda as dúvidas usando só o CONHECIMENTO fornecido. Não invente recurso,
  preço, prazo ou integração. Se não souber, diga que a equipe explica certinho.

A OFERTA DE REPASSE (o objetivo)
- Quando a pessoa já entendeu o valor e demonstrou interesse real, ofereça no
  espírito desta frase: "Posso passar teu contato pra nossa equipe entrar em
  contato e te mostrar certinho como funciona?".
- Não ofereça cedo demais (deixe ela entender o Klink primeiro). Não repita a
  oferta em toda mensagem.

QUANDO O LEAD ACEITAR
- Se a pessoa aceitar repassar o contato (ex.: "sim", "pode", "quero", "claro",
  "bora", "manda"), responda confirmando de forma calorosa que a equipe vai chamar,
  e marque lead_aceitou_contato = true.
- Só marque lead_aceitou_contato = true quando ela REALMENTE aceitar o repasse — não
  por entusiasmo genérico nem por ela só ter feito uma pergunta.
- Preencha resumo_lead com o que você descobriu (tipo de negócio, tamanho/nº de
  mesas, cidade, o que usa hoje, nível de interesse) — em 1 ou 2 frases, pro time
  humano já chegar sabendo com quem fala.

CAMPOS
- resposta: a mensagem que será enviada ao lead no WhatsApp.
- lead_aceitou_contato: true só no momento em que ela aceita o repasse do contato.
- nome_lead: o nome da pessoa ou do bar, se aparecer; senão "".
- resumo_lead: resumo curto pro time humano, quando houver; senão "".
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "resposta": {"type": "string"},
        "lead_aceitou_contato": {"type": "boolean"},
        "nome_lead": {"type": "string"},
        "resumo_lead": {"type": "string"},
    },
    "required": ["resposta", "lead_aceitou_contato", "nome_lead", "resumo_lead"],
}

# Resposta de emergência se a OpenAI não estiver configurada ou engasgar: o lead
# nunca fica no vácuo, mas também não disparamos alerta por engano.
FALLBACK = {
    "resposta": (
        "Opa, tudo bem? Aqui é o Klink 🛎️ Me conta rapidinho: "
        "você tem um bar ou restaurante? Aí já te explico como a gente faz "
        "o pedido chegar mais rápido na sua operação."
    ),
    "lead_aceitou_contato": False,
    "nome_lead": "",
    "resumo_lead": "",
}


class SDRAgent:
    def __init__(self, settings: Settings):
        self.settings = settings

    def responder(
        self,
        *,
        history: list[dict[str, Any]],
        mensagem: str,
        nome: str | None = None,
    ) -> dict[str, Any]:
        """Gera a resposta do agente para a última mensagem do lead.

        history: mensagens anteriores [{autor: 'lead'|'agente', texto: str}, ...].
        Devolve sempre um dict no formato do SCHEMA (cai no FALLBACK se a IA falhar).
        """
        if not self.settings.has_openai:
            return dict(FALLBACK)

        try:
            from openai import OpenAI
        except ImportError:
            return dict(FALLBACK)

        linhas = []
        for m in history:
            quem = "Lead" if m.get("autor") == "lead" else "Klink"
            texto = (m.get("texto") or "").strip()
            if texto:
                linhas.append(f"{quem}: {texto}")
        transcript = "\n".join(linhas) if linhas else "(início da conversa)"

        nome_hint = f"\nNome conhecido do contato: {nome}\n" if nome else "\n"

        prompt = (
            INSTRUCOES
            + "\n\nCONHECIMENTO DO KLINK:\n"
            + CONHECIMENTO
            + nome_hint
            + "\nCONVERSA ATÉ AQUI:\n"
            + transcript
            + f"\n\nNova mensagem do lead: {mensagem}\n"
            + "Responda agora, no formato JSON pedido."
        )

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=max(self.settings.openai_timeout_seconds, 25),
            max_retries=1,
        )
        try:
            response = client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "sdr_resposta",
                        "strict": True,
                        "schema": SCHEMA,
                    }
                },
            )
        except Exception:
            return dict(FALLBACK)

        output_text = getattr(response, "output_text", None)
        if not output_text:
            return dict(FALLBACK)
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError:
            return dict(FALLBACK)

        # Blindagem: garante o formato e tipos, mesmo se o modelo escorregar.
        return {
            "resposta": str(data.get("resposta") or FALLBACK["resposta"]).strip(),
            "lead_aceitou_contato": bool(data.get("lead_aceitou_contato")),
            "nome_lead": str(data.get("nome_lead") or "").strip(),
            "resumo_lead": str(data.get("resumo_lead") or "").strip(),
        }
