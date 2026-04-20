"""Weather tool definitions for the agent.

Provides current conditions and forecast data via the Open-Meteo API.
Both tools are READ_ONLY — they fetch public weather data with no
side effects.

Registered tools:
  - get_current_weather  (READ_ONLY) -- current conditions
  - get_weather_forecast (READ_ONLY) -- hourly forecast for a date
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import weather as weather_service


class GetWeatherForecastInput(BaseModel):
    date: str | None = Field(
        None, description="Date to forecast (YYYY-MM-DD). Defaults to today."
    )


@tool(
    tier=ActionTier.READ_ONLY,
    category="weather",
    embedding_text=(
        "weather: get_current_weather — what's the weather right now, "
        "current temperature, is it raining, is it cold, is it hot, "
        "weather conditions, humidity, wind, feels like outside"
    ),
)
async def get_current_weather(db: AsyncSession) -> dict:
    """Get current weather conditions.

    Temperature, feels-like, humidity, wind speed, and conditions for the
    user's configured location.
    """
    return await weather_service.get_current_weather()


@tool(
    tier=ActionTier.READ_ONLY,
    category="weather",
    embedding_text=(
        "weather: get_weather_forecast — will it rain today, tomorrow's weather, "
        "hourly forecast, temperature today, precipitation, "
        "should I bring an umbrella, is it going to snow, "
        "weather this afternoon, weekend forecast, outdoor plans"
    ),
)
async def get_weather_forecast(db: AsyncSession, input: GetWeatherForecastInput) -> dict:
    """Get the hourly weather forecast for a specific date.

    Temperature, precipitation probability, conditions, and wind for each
    hour. Defaults to today if no date is provided.
    """
    return await weather_service.get_forecast(date=input.date)
