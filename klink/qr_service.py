from __future__ import annotations

from urllib.parse import quote

from .config import Settings
from .table_session_service import TableSessionService


class QRService:
    def __init__(self, settings: Settings, table_sessions: TableSessionService):
        self.settings = settings
        self.table_sessions = table_sessions

    # Telefone-placeholder gravado pelo seed de demonstração. Não é um número real,
    # então deve ser ignorado em favor do número configurado/ambiente.
    _PLACEHOLDER_PHONE = "5500000000000"

    def bot_phone(self) -> str:
        """Número do WhatsApp do bot para os links do QR.

        Prioriza o número cadastrado pelo dono na tela de Configurações; se não
        houver um número real, usa o configurado por variável de ambiente.
        """
        phone = ""
        try:
            restaurant = self.table_sessions.restaurant()
            phone = "".join(ch for ch in (restaurant.get("telefone_whatsapp") or "") if ch.isdigit())
        except Exception:  # pragma: no cover - sem restaurante cadastrado
            phone = ""
        if phone and phone != self._PLACEHOLDER_PHONE and phone.strip("0"):
            return phone
        return self.settings.whatsapp_phone

    def whatsapp_link_for_table(self, table_number: int) -> str:
        text = quote(f"Mesa {table_number}")
        phone = self.bot_phone()
        if not phone:
            return f"https://wa.me/?text={text}"
        return f"https://wa.me/{phone}?text={text}"

    def public_qr_url(self, token: str) -> str:
        return f"{self.settings.public_base_url.rstrip('/')}/qr/{token}"

    def resolve_redirect(self, token: str) -> str | None:
        table = self.table_sessions.table_by_token(token)
        if not table:
            return None
        return self.whatsapp_link_for_table(int(table["numero"]))

