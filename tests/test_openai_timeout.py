from __future__ import annotations

import unittest
from unittest import mock

from klink.config import Settings
from klink.openai_interpreter import OpenAIInterpreter


def make_settings(**overrides) -> Settings:
    base = dict(
        database_path=":memory:",
        public_base_url="http://localhost:5000",
        whatsapp_phone="",
        evolution_api_url="",
        evolution_api_key="",
        evolution_instance="",
        openai_api_key="sk-teste",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        supabase_url="",
        supabase_service_role_key="",
        admin_token="",
        dashboard_user="admin",
        dashboard_password="",
    )
    base.update(overrides)
    return Settings(**base)


class OpenAITimeoutTest(unittest.TestCase):
    """Sem timeout, o SDK da OpenAI espera até 600s e cada mensagem presa ocupa
    uma das 8 threads do gunicorn — 8 mensagens presas congelam o app inteiro.
    Estes testes provam que o cliente é criado com timeout curto e sem retry."""

    def test_interpretador_cria_cliente_com_timeout(self):
        interpreter = OpenAIInterpreter(make_settings())
        with mock.patch("openai.OpenAI") as fake_openai:
            fake_openai.return_value.responses.create.side_effect = RuntimeError("rede caiu")
            result = interpreter.interpret(message="duas brahmas", table_number=5, menu_items=[])
        self.assertIsNone(result)  # falha vira fallback, nunca erro pro cliente
        _, kwargs = fake_openai.call_args
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["max_retries"], 0)

    def test_timeout_configuravel_por_env(self):
        interpreter = OpenAIInterpreter(make_settings(openai_timeout_seconds=3))
        with mock.patch("openai.OpenAI") as fake_openai:
            fake_openai.return_value.responses.create.side_effect = RuntimeError("rede caiu")
            interpreter.interpret(message="oi", table_number=1, menu_items=[])
        _, kwargs = fake_openai.call_args
        self.assertEqual(kwargs["timeout"], 3)

    def test_transcricao_cria_cliente_com_timeout(self):
        from klink.audio_service import AudioService

        service = AudioService(make_settings())
        with mock.patch("openai.OpenAI") as fake_openai:
            fake_openai.return_value.audio.transcriptions.create.return_value = "duas brahmas"
            text = service.transcribe_bytes(b"fake-audio", "audio/ogg", 5)
        self.assertEqual(text, "duas brahmas")
        _, kwargs = fake_openai.call_args
        self.assertEqual(kwargs["timeout"], 20)
        self.assertEqual(kwargs["max_retries"], 0)

    def test_settings_lem_timeout_do_ambiente(self):
        import importlib
        import os

        prev = {
            "KLINK_OPENAI_TIMEOUT": os.environ.get("KLINK_OPENAI_TIMEOUT"),
            "KLINK_OPENAI_TRANSCRIPTION_TIMEOUT": os.environ.get(
                "KLINK_OPENAI_TRANSCRIPTION_TIMEOUT"
            ),
        }
        os.environ["KLINK_OPENAI_TIMEOUT"] = "7"
        os.environ["KLINK_OPENAI_TRANSCRIPTION_TIMEOUT"] = "33"
        try:
            from klink import config as config_module

            importlib.reload(config_module)
            settings = config_module.get_settings()
            self.assertEqual(settings.openai_timeout_seconds, 7)
            self.assertEqual(settings.openai_transcription_timeout_seconds, 33)
        finally:
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
