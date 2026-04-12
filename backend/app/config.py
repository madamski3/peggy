"""Application configuration, loaded from environment variables / .env file.

All settings have defaults for local development. In production, they're
overridden via the .env file mounted into the Docker container.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://assistant:assistant@localhost/assistant"

    # Anthropic API
    anthropic_api_key: str = ""

    # Google Calendar OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://peggy.michaeladamski.com:3002/api/auth/google/callback"
    google_calendar_id: str = "primary"

    # OpenAI (embeddings)
    openai_api_key: str = ""

    # Frontend
    frontend_base_url: str = "http://peggy.michaeladamski.com:3002"

    # ntfy push notifications
    ntfy_base_url: str = "http://ntfy:80"
    ntfy_topic: str = "assistant"

    # Proactive job feature flags
    morning_briefing_enabled: bool = True
    deadline_warning_enabled: bool = True
    key_date_alert_enabled: bool = True

    model_config = {"env_file": ".env"}


settings = Settings()
