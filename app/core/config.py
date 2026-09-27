from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Contador de Inventario Totto API"
    api_prefix: str = "/api/v1"
    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]
    # Tamaño máximo aceptado para archivos .xlsx subidos (bytes).
    max_upload_bytes: int = 15 * 1024 * 1024

    # Autenticación (cookie httpOnly con JWT)
    secret_key: str = Field(min_length=32)
    session_hours: int = 12  # una jornada de tienda
    cookie_name: str = "totto_session"
    cookie_secure: bool = False  # true en producción (HTTPS)
    cookie_samesite: str = "lax"
    max_failed_logins: int = 5
    lockout_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
