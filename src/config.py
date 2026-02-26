from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    environment: Literal["development", "production", "test"] = "development"
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    # Database
    database_url: str
    encryption_key: str = ""

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Shopify (client credentials — tokens auto-refresh every 24h)
    shopify_client_id: str = ""
    shopify_secret_key: str = ""
    shopify_store_url: str = ""

    # Google OAuth (social login)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Meta Marketing API (also used for Facebook social login)
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_short_lived_token: str = ""
    meta_ad_account_id: str = ""

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""

    # Monitoring
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment == "production":
            if not self.encryption_key:
                raise ValueError("ENCRYPTION_KEY is required in production environment.")
            if not self.openai_api_key and not self.anthropic_api_key and not self.google_api_key:
                raise ValueError("At least one LLM API key must be provided in production.")
        return self


settings = Settings()
