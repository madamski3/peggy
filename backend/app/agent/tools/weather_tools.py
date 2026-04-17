"""Weather tool definitions for the agent.

Provides current conditions and forecast data via the Open-Meteo API.
Both tools are READ_ONLY — they fetch public weather data with no
side effects.

Registered tools:
  - get_current_weather  (READ_ONLY) -- current conditions
  - get_weather_forecast (READ_ONLY) -- hourly forecast for a date
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import weather as weather_service


# ── Handlers ──────────────────────────────────────────────────────


async def handle_get_current_weather(db: AsyncSession, **kwargs: Any) -> dict:
    return await weather_service.get_current_weather()


async def handle_get_weather_forecast(db: AsyncSession, **kwargs: Any) -> dict:
    return await weather_service.get_forecast(date=kwargs.get("date"))


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_current_weather",
    description=(
        "Get current weather conditions — temperature, feels-like, humidity, "
        "wind speed, and conditions. Uses the user's configured location."
    ),
    embedding_text=(
        "weather: get_current_weather — what's the weather right now, "
        "current temperature, is it raining, is it cold, is it hot, "
        "weather conditions, humidity, wind, feels like outside"
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_current_weather,
    category="weather",
))

register_tool(ToolDefinition(
    name="get_weather_forecast",
    description=(
        "Get the hourly weather forecast for a specific date — temperature, "
        "precipitation probability, conditions, and wind for each hour. "
        "Defaults to today if no date is provided."
    ),
    embedding_text=(
        "weather: get_weather_forecast — will it rain today, tomorrow's weather, "
        "hourly forecast, temperature today, precipitation, "
        "should I bring an umbrella, is it going to snow, "
        "weather this afternoon, weekend forecast, outdoor plans"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date to forecast (YYYY-MM-DD). Defaults to today.",
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_weather_forecast,
    category="weather",
))
