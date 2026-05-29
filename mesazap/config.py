from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    database_path: str
    public_base_url: str
    whatsapp_phone: str
    evolution_api_url: str
    evolution_api_key: str
    evolution_instance: str
    openai_api_key: str
    openai_model: str
    openai_transcription_model: str
    supabase_url: str
    supabase_service_role_key: str
    admin_token: str
    dashboard_user: str
    dashboard_password: str
    max_audio_seconds: int = 35
    evolution_daily_limit: int = 200
    require_table_validation: bool = False
    session_idle_ttl_hours: int = 6
    # Modo de desenvolvimento explicito. Quando True, as rotas /admin/* podem
    # ser usadas sem MESAZAP_ADMIN_TOKEN. Em producao deve ficar False (padrao),
    # para que falta de token signifique acesso negado, nao acesso liberado.
    dev_mode: bool = False

    @property
    def dashboard_auth_enabled(self) -> bool:
        return bool(self.dashboard_password)

    @property
    def has_evolution(self) -> bool:
        return bool(self.evolution_api_url and self.evolution_api_key and self.evolution_instance)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_settings() -> Settings:
    load_env_file()
    return Settings(
        database_path=os.getenv("MESAZAP_DATABASE", "mesazap.local.db"),
        public_base_url=os.getenv("MESAZAP_PUBLIC_BASE_URL", "http://localhost:5000"),
        whatsapp_phone=os.getenv("WHATSAPP_PHONE", ""),
        evolution_api_url=os.getenv("EVOLUTION_API_URL", "").rstrip("/"),
        evolution_api_key=os.getenv("EVOLUTION_API_KEY", ""),
        evolution_instance=os.getenv("EVOLUTION_INSTANCE", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_transcription_model=os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"
        ),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        admin_token=os.getenv("MESAZAP_ADMIN_TOKEN", ""),
        dashboard_user=os.getenv("MESAZAP_DASHBOARD_USER", "admin"),
        dashboard_password=os.getenv("MESAZAP_DASHBOARD_PASSWORD", ""),
        evolution_daily_limit=_int_env("EVOLUTION_DAILY_LIMIT", 200),
        require_table_validation=_bool_env("MESAZAP_REQUIRE_TABLE_VALIDATION", False),
        session_idle_ttl_hours=_int_env("MESAZAP_SESSION_IDLE_TTL_HOURS", 6),
        dev_mode=_bool_env("MESAZAP_DEV_MODE", False),
    )

