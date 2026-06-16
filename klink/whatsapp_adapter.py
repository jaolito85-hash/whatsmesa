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
    # Nome do evento Evolution normalizado (ex.: "messages.upsert" no clássico,
    # "message" no Evolution Go). Vazio quando o payload não traz o campo.
    event: str = ""
    # Nome de quem mandou (WhatsApp pushName). Centralizado aqui porque cada
    # dialeto guarda em lugar diferente (data.pushName x data.Info.PushName).
    push_name: str = ""


def _jid_to_str(value: Any) -> str:
    """Converte um JID para a string 'user@server'.

    O Evolution Go (whatsmeow) já serializa o JID como string graças ao
    MarshalText. Mas, por segurança contra versões que serializem o struct,
    também aceitamos o objeto {User, Server}.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        user = value.get("User") or value.get("user") or ""
        server = value.get("Server") or value.get("server") or ""
        if user and server:
            return f"{user}@{server}"
    return ""


class WhatsAppAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def normalize_evolution_payload(self, payload: dict[str, Any]) -> InboundMessage:
        data = payload.get("data") or payload
        # Dois dialetos no MESMO método:
        #  - Evolution clássico (Baileys): data.key.remoteJid, data.message.*, data.pushName
        #  - Evolution Go (whatsmeow): data.Info.Chat (string "user@server"),
        #    data.Message.*, data.Info.PushName — tudo em PascalCase. (O garçom usa o
        #    clássico, o agente SDR usa o Go; por isso os dois convivem aqui.)
        key = data.get("key") or {}
        info = data.get("Info") or data.get("info") or {}
        message = data.get("message") or data.get("Message") or {}

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

        # Duração pode vir como string suja de payloads malformados; não pode
        # estourar aqui (estouraria como HTTP 500 antes de qualquer proteção).
        try:
            duration_seconds = int(duration) if duration else None
        except (TypeError, ValueError):
            duration_seconds = None

        remote_jid = (
            key.get("remoteJid")
            or _jid_to_str(info.get("Chat") or info.get("chat"))
            or _jid_to_str(info.get("Sender") or info.get("sender"))
            or data.get("remote_jid")
            or payload.get("remote_jid")
            or ""
        )

        # fromMe: no clássico fica em key.fromMe; no Go em data.Info.IsFromMe.
        if "fromMe" in key:
            from_me = bool(key.get("fromMe"))
        elif "IsFromMe" in info:
            from_me = bool(info.get("IsFromMe"))
        else:
            from_me = bool(info.get("isFromMe"))

        message_id = (
            key.get("id")
            or info.get("ID")
            or info.get("id")
            or data.get("message_id")
            or payload.get("message_id")
            or uuid4().hex
        )

        push_name = (
            data.get("pushName")
            or info.get("PushName")
            or info.get("pushName")
            or payload.get("pushName")
            or ""
        )

        return InboundMessage(
            message_id=message_id,
            remote_jid=remote_jid,
            text=text,
            tipo=tipo,
            audio_url=audio_url,
            audio_base64=audio_base64,
            audio_mimetype=audio_mimetype,
            duration_seconds=duration_seconds,
            payload=payload,
            from_me=from_me,
            event=event,
            push_name=push_name,
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

