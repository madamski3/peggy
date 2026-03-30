"""Application configuration, loaded from environment variables / .env file.

All settings have defaults for local development. In production, they're
overridden via the .env file mounted into the Docker container.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://assistant:assistant@localhost/assistant"
    system_prompt_version: str = "v1"

    # Anthropic API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    agent_max_tool_rounds: int = 10

    # Google Calendar OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://peggy.michaeladamski.com:3002/api/auth/google/callback"
    google_calendar_id: str = "primary"

    # ntfy push notifications
    ntfy_base_url: str = "http://ntfy:80"
    ntfy_topic: str = "assistant"
    notification_poll_seconds: int = 30

    # Proactive job schedules
    morning_briefing_enabled: bool = True
    morning_briefing_default_hour: int = 7
    morning_briefing_default_minute: int = 0
    deadline_warning_enabled: bool = True
    deadline_warning_hour: int = 10
    deadline_warning_days_ahead: int = 3
    key_date_alert_enabled: bool = True
    key_date_alert_hour: int = 9
    key_date_alert_days_ahead: int = 7

    model_config = {"env_file": ".env"}


settings = Settings()
