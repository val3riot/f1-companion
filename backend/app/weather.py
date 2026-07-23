from datetime import date
from typing import Any

import httpx

from .cache import AsyncTTLCache
from .config import settings


class WeatherClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.open_meteo_base_url,
            timeout=httpx.Timeout(15),
            headers={"User-Agent": "f1-companion/0.3"},
        )
        self._archive_http = httpx.AsyncClient(
            base_url=settings.open_meteo_archive_url,
            timeout=httpx.Timeout(15),
            headers={"User-Agent": "f1-companion/0.3"},
        )
        self._cache = AsyncTTLCache()

    async def close(self) -> None:
        await self._http.aclose()
        await self._archive_http.aclose()

    async def forecast(
        self,
        latitude: float,
        longitude: float,
        race_date: date,
    ) -> dict[str, Any]:
        key = f"{latitude}:{longitude}:{race_date.isoformat()}"

        async def fetch() -> dict[str, Any]:
            response = await self._http.get(
                "/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max,wind_speed_10m_max"
                    ),
                    "timezone": "UTC",
                    "forecast_days": 16,
                },
            )
            response.raise_for_status()
            return response.json()

        payload = await self._cache.get_or_set(key, fetch, ttl=1800)
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        race_day = race_date.isoformat()
        if race_day not in dates:
            return {
                "available": False,
                "reason": "Gara fuori dall'orizzonte meteo di 16 giorni",
            }
        index = dates.index(race_day)
        return {
            "available": True,
            "source": "Open-Meteo",
            "temperature_min": daily["temperature_2m_min"][index],
            "temperature_max": daily["temperature_2m_max"][index],
            "rain_probability": daily[
                "precipitation_probability_max"
            ][index],
            "wind_speed_max": daily["wind_speed_10m_max"][index],
        }

    async def historical_temperature(
        self,
        latitude: float,
        longitude: float,
        race_date: date,
    ) -> float | None:
        key = f"history:{latitude}:{longitude}:{race_date.isoformat()}"

        async def fetch() -> dict[str, Any]:
            response = await self._archive_http.get(
                "/archive",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": race_date.isoformat(),
                    "end_date": race_date.isoformat(),
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "timezone": "UTC",
                },
            )
            response.raise_for_status()
            return response.json()

        payload = await self._cache.get_or_set(key, fetch, ttl=2592000)
        daily = payload.get("daily", {})
        minimum = (daily.get("temperature_2m_min") or [None])[0]
        maximum = (daily.get("temperature_2m_max") or [None])[0]
        if minimum is None or maximum is None:
            return None
        return round((float(minimum) + float(maximum)) / 2, 1)
