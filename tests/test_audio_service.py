from __future__ import annotations

import unittest

from mesazap.audio_service import AudioService, SUPPORTED_AUDIO_SUFFIXES
from mesazap.config import Settings


def make_settings() -> Settings:
    return Settings(
        database_path=":memory:",
        public_base_url="http://localhost:5000",
        whatsapp_phone="",
        evolution_api_url="",
        evolution_api_key="",
        evolution_instance="",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        supabase_url="",
        supabase_service_role_key="",
        admin_token="",
        dashboard_user="admin",
        dashboard_password="",
    )


class AudioServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = AudioService(make_settings())

    def test_resolve_suffix_handles_ogg(self):
        self.assertEqual(
            self.service.resolve_suffix("https://cdn.evo.com/audio/abc.ogg"),
            ".ogg",
        )

    def test_resolve_suffix_handles_oga(self):
        self.assertEqual(
            self.service.resolve_suffix("https://cdn.evo.com/audio/abc.oga?x=1"),
            ".oga",
        )

    def test_resolve_suffix_opus_aliases_to_ogg(self):
        self.assertEqual(
            self.service.resolve_suffix("https://cdn.evo.com/audio/abc.opus"),
            ".ogg",
        )

    def test_resolve_suffix_query_string_ignored(self):
        self.assertEqual(
            self.service.resolve_suffix("https://cdn.evo.com/audio/abc.webm?token=xyz"),
            ".webm",
        )

    def test_resolve_suffix_defaults_to_webm(self):
        self.assertEqual(
            self.service.resolve_suffix("https://cdn.evo.com/audio/file-no-extension"),
            ".webm",
        )

    def test_supported_suffixes_cover_whatsapp_defaults(self):
        for suffix in (".ogg", ".oga", ".webm", ".m4a", ".mp3"):
            self.assertIn(suffix, SUPPORTED_AUDIO_SUFFIXES)


if __name__ == "__main__":
    unittest.main()
