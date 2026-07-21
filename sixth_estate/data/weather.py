"""weather.gov adapter — three-day US forecast for a gridpoint.

weather.gov is a free public API but requires a descriptive User-Agent. Callers
resolve a lat/lon to a forecast gridpoint URL out of band, or pass one directly.
`transport` injectable for tests.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source

# Gridpoint from config (default: Flint, MI). Override with SIXTHE_WEATHER_FORECAST_URL.
DEFAULT_FORECAST_URL = config.WEATHER_FORECAST_URL


def fetch_forecast(forecast_url: Optional[str] = None, days: int = 3,
                   transport: Optional[Callable] = None) -> list[DataMetric]:
    url = forecast_url or DEFAULT_FORECAST_URL
    if transport is not None:
        data = transport(url)
    else:
        data = get_json(url, headers={"User-Agent": "6E-bot/1.0 (contact: news@the6thestate.net)"})
    periods = (data.get("properties", {}) or {}).get("periods", []) or []
    out: list[DataMetric] = []
    for p in periods[: days * 2]:  # day+night pairs; cap
        name = p.get("name", "")
        temp = p.get("temperature", "")
        unit = p.get("temperatureUnit", "")
        short = p.get("shortForecast", "")
        out.append(DataMetric(
            label=name, value=f"{temp}°{unit} — {short}".strip(" —"),
            as_of=p.get("startTime", "")[:10],
            source=Source(url=url, title="NWS forecast", publisher="weather.gov",
                          published=p.get("startTime", "")[:10]),
        ))
    return out[:days]
