from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

from .config import Settings


SUPPORTED_AUDIO_SUFFIXES = {
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
    ".ogg",
    ".wav",
    ".webm",
}

SUFFIX_ALIASES = {
    ".opus": ".ogg",
}


class AudioService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve_suffix(self, audio_url: str) -> str:
        raw = (Path(audio_url.split("?", 1)[0]).suffix or ".webm").lower()
        return SUFFIX_ALIASES.get(raw, raw)

    def transcribe_url(self, audio_url: str, duration_seconds: int | None = None) -> str:
        if duration_seconds and duration_seconds > self.settings.max_audio_seconds:
            raise ValueError(
                f"Audio muito longo para o MVP. Envie ate {self.settings.max_audio_seconds} segundos."
            )
        if not self.settings.has_openai:
            raise RuntimeError("OPENAI_API_KEY nao configurada para transcrever audio.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Pacote openai nao instalado.") from exc

        suffix = self.resolve_suffix(audio_url)
        if suffix not in SUPPORTED_AUDIO_SUFFIXES:
            accepted = ", ".join(sorted(SUPPORTED_AUDIO_SUFFIXES))
            raise ValueError(f"Formato de audio nao suportado ({suffix}). Use {accepted}.")

        with urllib.request.urlopen(audio_url, timeout=30) as response:
            content = response.read()
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("Audio maior que 25 MB.")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
            handle.write(content)
            handle.flush()
            client = OpenAI(api_key=self.settings.openai_api_key)
            with open(handle.name, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=self.settings.openai_transcription_model,
                    file=audio_file,
                    response_format="text",
                )
        return str(transcript).strip()
