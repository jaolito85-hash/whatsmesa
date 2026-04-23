from __future__ import annotations

import json
from typing import Any

from .config import Settings


class OpenAIInterpreter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def interpret(
        self,
        *,
        message: str,
        table_number: int,
        menu_items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self.settings.has_openai:
            return None

        try:
            from openai import OpenAI
        except ImportError:
            return None

        menu_lines = [
            f"- {item['nome']} | setor={item['setor']} | disponivel={bool(item['disponivel'])} | aliases={', '.join(item.get('aliases', []))}"
            for item in menu_items
        ]
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["order", "service", "close_account", "repeat", "unknown"],
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                            "notes": {"type": "string"},
                        },
                        "required": ["name", "quantity", "notes"],
                    },
                },
                "service_description": {"type": "string"},
                "clarification_question": {"type": "string"},
            },
            "required": ["intent", "items", "service_description", "clarification_question"],
        }
        prompt = (
            "Voce e o garcom digital de um restaurante. "
            "Entenda mensagens em portugues, ingles e espanhol, inclusive frases misturadas. "
            "Classifique a mensagem do cliente e extraia apenas itens que existem no cardapio. "
            "Nunca invente produto. Se faltar detalhe, preencha clarification_question.\n\n"
            f"Mesa: {table_number}\n"
            "Cardapio interno:\n"
            + "\n".join(menu_lines)
            + f"\n\nMensagem: {message}"
        )

        client = OpenAI(api_key=self.settings.openai_api_key)
        try:
            response = client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "restaurant_intent",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )
        except Exception:
            return None

        output_text = getattr(response, "output_text", None)
        if not output_text:
            return None
        try:
            return json.loads(output_text)
        except json.JSONDecodeError:
            return None
