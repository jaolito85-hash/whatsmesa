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
    duration_seconds: int | None
    payload: dict[str, Any]


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
        duration = audio.get("seconds") or data.get("duration_seconds") or payload.get("duration_seconds")
        tipo = "audio" if audio_url and not text else "texto"

        return InboundMessage(
            message_id=key.get("id") or data.get("message_id") or payload.get("message_id") or uuid4().hex,
            remote_jid=key.get("remoteJid") or data.get("remote_jid") or payload.get("remote_jid") or "",
            text=text,
            tipo=tipo,
            audio_url=audio_url,
            duration_seconds=int(duration) if duration else None,
            payload=payload,
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

