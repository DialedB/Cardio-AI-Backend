"""Environment-backed application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    app_name: str = Field(default="cardiosmart-backend", validation_alias="APP_NAME")
    app_env: Literal["local", "development", "test", "staging", "production"] = Field(
        default="local", validation_alias="APP_ENV"
    )
    debug: bool = Field(default=False, validation_alias="DEBUG")
    database_url: str = Field(
        default="postgresql+psycopg://cardiosmart:cardiosmart@localhost:5432/cardiosmart",
        validation_alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
