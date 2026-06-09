from __future__ import annotations

import ipaddress
import socket
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings


def _ensure_public_url(url: str) -> None:
    """Anti-SSRF: recusa baixar de URLs que apontem para a rede interna.

    O `audio_url` vem do payload do webhook. Mesmo com o webhook protegido, esta é
    uma barreira extra contra um payload malicioso pedir um fetch para
    169.254.169.254 (metadados de cloud), localhost ou IPs privados.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL de audio invalida (esquema nao permitido).")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL de audio sem host.")
    ips: set[ipaddress._BaseAddress] = set()
    try:
        ips.add(ipaddress.ip_address(host))  # host ja e um IP literal
    except ValueError:
        try:
            for info in socket.getaddrinfo(host, None):
                ips.add(ipaddress.ip_address(info[4][0]))
        except OSError:
            return  # nao resolveu: deixa o urlopen falhar naturalmente
    for ip in ips:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise ValueError("URL de audio aponta para endereco interno (bloqueado).")


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

MIMETYPE_TO_SUFFIX = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".mp4",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
}


class AudioService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve_suffix(self, audio_url: str) -> str:
        raw = (Path(audio_url.split("?", 1)[0]).suffix or ".webm").lower()
        return SUFFIX_ALIASES.get(raw, raw)

    def suffix_from_mimetype(self, mimetype: str | None) -> str | None:
        if not mimetype:
            return None
        primary = mimetype.split(";", 1)[0].strip().lower()
        return MIMETYPE_TO_SUFFIX.get(primary)

    def transcribe_url(self, audio_url: str, duration_seconds: int | None = None) -> str:
        if duration_seconds and duration_seconds > self.settings.max_audio_seconds:
            raise ValueError(
                f"Audio muito longo para o MVP. Envie ate {self.settings.max_audio_seconds} segundos."
            )

        suffix = self.resolve_suffix(audio_url)
        if suffix not in SUPPORTED_AUDIO_SUFFIXES:
            accepted = ", ".join(sorted(SUPPORTED_AUDIO_SUFFIXES))
            raise ValueError(f"Formato de audio nao suportado ({suffix}). Use {accepted}.")

        _ensure_public_url(audio_url)
        with urllib.request.urlopen(audio_url, timeout=30) as response:
            content = response.read()
        return self._transcribe_bytes(content, suffix, duration_seconds)

    def transcribe_bytes(
        self,
        content: bytes,
        mimetype: str | None = None,
        duration_seconds: int | None = None,
    ) -> str:
        suffix = self.suffix_from_mimetype(mimetype) or ".ogg"
        if suffix not in SUPPORTED_AUDIO_SUFFIXES:
            accepted = ", ".join(sorted(SUPPORTED_AUDIO_SUFFIXES))
            raise ValueError(f"Formato de audio nao suportado ({suffix}). Use {accepted}.")
        return self._transcribe_bytes(content, suffix, duration_seconds)

    def _transcribe_bytes(
        self,
        content: bytes,
        suffix: str,
        duration_seconds: int | None,
    ) -> str:
        if duration_seconds and duration_seconds > self.settings.max_audio_seconds:
            raise ValueError(
                f"Audio muito longo para o MVP. Envie ate {self.settings.max_audio_seconds} segundos."
            )
        if not self.settings.has_openai:
            raise RuntimeError("OPENAI_API_KEY nao configurada para transcrever audio.")
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("Audio maior que 25 MB.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Pacote openai nao instalado.") from exc

        # delete=False + unlink manual: o Windows não deixa reabrir um arquivo
        # temporário ainda aberto (em Linux funciona; assim funciona nos dois).
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(content)
                tmp_path = Path(handle.name)
            # timeout limitado + sem retry: melhor responder rápido "manda por
            # texto" do que segurar uma thread do gunicorn por minutos.
            client = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_transcription_timeout_seconds,
                max_retries=0,
            )
            with open(tmp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=self.settings.openai_transcription_model,
                    file=audio_file,
                    response_format="text",
                )
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        return str(transcript).strip()
