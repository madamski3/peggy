"""Weather service using the Open-Meteo API.

Provides current conditions and hourly forecasts. Open-Meteo is free,
requires no API key, and has generous rate limits.

The user's location (latitude/longitude) is resolved from config defaults.
"""

import logging
from datetime import datetime

import httpx

from app.config import settings
from app.globals import get_cached_timezone

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → human-readable descriptions
_WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _describe_code(code: int) -> str:
    return _WMO_DESCRIPTIONS.get(code, f"Unknown ({code})")


async def get_current_weather() -> dict:
    """Fetch current weather conditions for the user's location.

    Returns a dict with temperature, conditions, wind speed, humidity,
    and apparent (feels-like) temperature.
    """
    params = {
        "latitude": settings.default_latitude,
        "longitude": settings.default_longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": str(get_cached_timezone()),
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current", {})
    return {
        "temperature_f": current.get("temperature_2m"),
        "feels_like_f": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_speed_mph": current.get("wind_speed_10m"),
        "conditions": _describe_code(current.get("weather_code", -1)),
        "time": current.get("time"),
    }


async def get_forecast(date: str | None = None) -> dict:
    """Fetch hourly forecast for a given date.

    Args:
        date: ISO date string (YYYY-MM-DD). Defaults to today.

    Returns a dict with the date, a list of hourly entries (temp,
    conditions, precipitation probability, wind), and a daily summary.
    """
    tz = get_cached_timezone()
    if not date:
        date = datetime.now(tz).strftime("%Y-%m-%d")

    params = {
        "latitude": settings.default_latitude,
        "longitude": settings.default_longitude,
        "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": str(get_cached_timezone()),
        "start_date": date,
        "end_date": date,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    # Build hourly entries (only waking hours 6am-11pm to keep it concise)
    hours = []
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precip_probs = hourly.get("precipitation_probability", [])
    codes = hourly.get("weather_code", [])
    winds = hourly.get("wind_speed_10m", [])

    for i, t in enumerate(times):
        hour = int(t[11:13]) if len(t) >= 13 else 0
        if 6 <= hour <= 23:
            hours.append({
                "time": t[11:16],  # "HH:MM"
                "temperature_f": temps[i] if i < len(temps) else None,
                "precipitation_probability_pct": precip_probs[i] if i < len(precip_probs) else None,
                "conditions": _describe_code(codes[i]) if i < len(codes) else "Unknown",
                "wind_speed_mph": winds[i] if i < len(winds) else None,
            })

    # Daily summary
    summary = {
        "date": date,
        "high_f": daily.get("temperature_2m_max", [None])[0],
        "low_f": daily.get("temperature_2m_min", [None])[0],
        "max_precipitation_probability_pct": daily.get("precipitation_probability_max", [None])[0],
        "conditions": _describe_code(daily.get("weather_code", [-1])[0]),
    }

    return {
        "date": date,
        "summary": summary,
        "hourly": hours,
    }
