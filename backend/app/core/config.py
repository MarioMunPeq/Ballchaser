"""Configuración de la aplicación, leída de variables de entorno."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la API.

    Los valores por defecto son solo para desarrollo local; en producción todos
    los secretos llegan por variable de entorno.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BallChaser API"
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=False, alias="LOG_JSON")

    database_url: str = Field(
        default="postgresql+psycopg://ballchaser:ballchaser@localhost:5432/ballchaser",
        alias="DATABASE_URL",
    )

    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    # Fase 1: verificación de ID tokens de Firebase.
    # Se prefiere el fichero (la clave de servicio que descargas de la consola)
    # porque el JSON es multilínea y en una variable de entorno hay que escaparlo
    # entero en una sola línea.
    firebase_credentials_file: str | None = Field(default=None, alias="FIREBASE_CREDENTIALS_FILE")
    firebase_credentials_json: str | None = Field(default=None, alias="FIREBASE_CREDENTIALS_JSON")

    # Fase 2: token de Ballchasing. Solo se usa en desarrollo para sondear la API;
    # en produccion cada usuario aporta el suyo y se guarda cifrado.
    ballchasing_api_key: str | None = Field(default=None, alias="BALLCASING_API_KEY")

    # Fase 2: cifrado del token de Ballchasing (clave base64 de 32 bytes).
    secret_encryption_key: str | None = Field(default=None, alias="SECRET_ENCRYPTION_KEY")
    secret_key_version: int = Field(default=1, alias="SECRET_KEY_VERSION")

    # Fase 3: proteccion del endpoint de cron llamado por GitHub Actions.
    cron_secret: str | None = Field(default=None, alias="CRON_SECRET")

    # Fase 6: exposition de métricas Prometheus (protegida).
    metrics_token: str | None = Field(default=None, alias="METRICS_TOKEN")


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada del proceso."""
    return Settings()


settings = get_settings()
