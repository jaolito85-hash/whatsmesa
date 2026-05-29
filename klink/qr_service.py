from __future__ import annotations

from urllib.parse import quote

from .config import Settings
from .table_session_service import TableSessionService


class QRService:
    def __init__(self, settings: Settings, table_sessions: TableSessionService):
        self.settings = settings
        self.table_sessions = table_sessions

    def whatsapp_link_for_table(self, table_number: int) -> str:
        text = quote(f"Mesa {table_number}")
        if not self.settings.whatsapp_phone:
            return f"https://wa.me/?text={text}"
        return f"https://wa.me/{self.settings.whatsapp_phone}?text={text}"

    def public_qr_url(self, token: str) -> str:
        return f"{self.settings.public_base_url.rstrip('/')}/qr/{token}"

    def resolve_redirect(self, token: str) -> str | None:
        table = self.table_sessions.table_by_token(token)
        if not table:
            return None
        return self.whatsapp_link_for_table(int(table["numero"]))

