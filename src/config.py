import logging

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, ValidationInfo

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    bot_token: str | None = None
    port: int = 10000
    database_url: str | None = None
    cron_secret: str | None = None
    redis_url: str | None = None
    admins_telegram_id: list[int] | None = None
    metrics_secret: str | None = None
    environment: str = "production"
    portal_semaphore_limit: int = 3
    portal_timeout_seconds: int = 30
    registration_cooldown_seconds: int = 300
    manual_scrape_cooldown_minutes: int = 30
    inactivity_notice_months: int = 9
    encryption_key: str | None = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("PORT must be a positive integer")
        return value

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("BOT_TOKEN is required")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("DATABASE_URL is required")
        return value
    

    # Log that the fields are None
    @field_validator("cron_secret", "redis_url", "admins_telegram_id", "metrics_secret")
    @classmethod
    def validate_optional_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            logging.warning(f"Warning: {info.field_name} field is None")
        return value

def load_settings() -> Settings:
    return Settings()
