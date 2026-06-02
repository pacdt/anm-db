"""
Configuracao centralizada do anm-db.

Carrega variaveis de ambiente (com fallback) e do arquivo .env na raiz do projeto.
Type-safe via pydantic-settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Raiz do projeto (dois niveis acima deste arquivo: anm_db/config.py -> anm_db/ -> raiz)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuracao global. Carrega do .env automaticamente."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    db_path: str = Field(default="anm.db", description="Caminho do arquivo SQLite")

    req_catalogo: int = Field(default=3, description="Requests por segundo para catalogo")
    req_episodios: int = Field(default=2, description="Requests por segundo para episodios")
    concurrency_catalogo: int = Field(default=3)
    concurrency_episodios: int = Field(default=3, description="Limite para 1 OCPU free tier")
    max_episodios_frente: int = Field(default=10)
    erros_consecutivos_limite: int = Field(default=2)
    delay_entre_batches: float = Field(default=2.0)
    delay_apos_429: float = Field(default=15.0)
    timeout_global: int = Field(default=30)

    gemini_api_key: str | None = Field(default=None, description="API key do Google Gemini")
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_rpm: int = Field(default=15, description="Requests por minuto (free tier)")
    gemini_rpd: int = Field(default=1500, description="Requests por dia (free tier)")
    translation_batch_size: int = Field(default=10)
    translation_enabled: bool = Field(default=True)

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    ffmpeg_path: str = Field(default="ffmpeg", description="Caminho do binario ffmpeg")
    download_chunk_size: int = Field(default=1024 * 64)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instancia singleton das configuracoes."""
    return Settings()


settings = get_settings()


def reload_settings() -> Settings:
    """Forca releitura do .env (util em testes)."""
    get_settings.cache_clear()
    global settings
    settings = get_settings()
    return settings
