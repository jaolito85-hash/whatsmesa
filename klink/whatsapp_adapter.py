from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .config import Settings


@dataclass(frozen=True)
class InboundMessage:
    message_id: str
    remote_jid: str
    text: str
    tipo: str
    audio_url: str | None
    audio_base64: str | None
    audio_mimetype: str | None
    duration_seconds: int | None
    payload: dict[str, Any]
    # Mensagem enviada pelo PRÓPRIO bot (key.fromMe). Precisa ser descartada no
    # webhook: sem isso, a resposta do bot volta como se fosse o cliente falando
    # e o bot responde a si mesmo em loop infinito — rajada de mensagens que o
    # WhatsApp pune com banimento do número.
    from_me: bool = False
    # Nome do evento Evolution normalizado (ex.: "messages.upsert"). Vazio quando
    # o payload não traz o campo (simulador/testes).
    event: str = ""


class WhatsAppAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def normalize_evolution_payload(self, payload: dict[str, Any]) -> InboundMessage:
        data = payload.get("data") or payload
        key = data.get("key") or {}
        message = data.get("message") or {}

        text = (
            message.get("conversation")
            or (message.get("extendedTextMessage") or {}).get("text")
            or data.get("text")
            or payload.get("text")
            or ""
        )
        audio = message.get("audioMessage") or {}
        audio_url = audio.get("url") or data.get("audio_url") or payload.get("audio_url")
        audio_base64 = (
            audio.get("base64")
            or message.get("base64")
            or data.get("base64")
            or data.get("media")
            or payload.get("base64")
        )
        audio_mimetype = audio.get("mimetype") or audio.get("mimeType")
        duration = audio.get("seconds") or data.get("duration_seconds") or payload.get("duration_seconds")
        has_audio = bool(audio_url or audio_base64 or audio.get("mediaKey"))
        tipo = "audio" if has_audio and not text else "texto"

        event = str(payload.get("event") or "").strip().lower().replace("_", ".")

        return InboundMessage(
            message_id=key.get("id") or data.get("message_id") or payload.get("message_id") or uuid4().hex,
            remote_jid=key.get("remoteJid") or data.get("remote_jid") or payload.get("remote_jid") or "",
            text=text,
            tipo=tipo,
            audio_url=audio_url,
            audio_base64=audio_base64,
            audio_mimetype=audio_mimetype,
            duration_seconds=int(duration) if duration else None,
            payload=payload,
            from_me=bool(key.get("fromMe")),
            event=event,
        )

    def send_message(self, remote_jid: str, text: str) -> dict[str, Any]:
        if not self.settings.has_evolution:
            return {"sent": False, "dry_run": True, "remote_jid": remote_jid, "text": text}

        url = (
            f"{self.settings.evolution_api_url}/message/sendText/"
            f"{self.settings.evolution_instance}"
        )
        body = json.dumps({"number": remote_jid, "text": text}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "apikey": self.settings.evolution_api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
        return {"sent": True, "response": response_body}

    def fetch_media_base64(self, message_id: str) -> tuple[str, str | None]:
        if not self.settings.has_evolution:
            raise RuntimeError("Evolution API nao configurada para baixar midia.")

        url = (
            f"{self.settings.evolution_api_url}/chat/getBase64FromMediaMessage/"
            f"{self.settings.evolution_instance}"
        )
        body = json.dumps({"message": {"key": {"id": message_id}}, "convertToMp4": False}).encode(
            "utf-8"
        )
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "apikey": self.settings.evolution_api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
        b64 = data.get("base64") or data.get("media") or ""
        if not b64:
            raise RuntimeError(f"Evolution nao retornou base64 para {message_id}: {data}")
        return b64, data.get("mimetype")

