"""FRED adapter — 30-year mortgage rate (MORTGAGE30US) and generic series.

Requires FRED_API_KEY (never logged). `transport` is injectable for tests.
Returns a DataMetric with a direct series URL and an as-of date.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source


def _series_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


def fetch_series(series_id: str, label: str, unit: str = "",
                 transport: Optional[Callable] = None,
                 api_key: Optional[str] = None) -> DataMetric:
    api_key = api_key if api_key is not None else config.FRED_API_KEY
    if transport is not None:
        data = transport(series_id)
    else:
        if not api_key:
            raise RuntimeError("FRED_API_KEY not set")
        url = (f"{config.FRED_API_BASE}/series/observations?series_id={series_id}"
               f"&api_key={api_key}&file_type=json&sort_order=desc&limit=1")
        data = get_json(url)
    obs = (data.get("observations") or [{}])[0]
    raw_value = obs.get("value", "")
    as_of = obs.get("date", "")
    # Cap numeric values at 2 decimal places for clean display.
    try:
        num = float(raw_value)
        # Use commas for large numbers (equities), plain for rates.
        if num >= 100:
            value = f"{num:,.2f}"
        else:
            value = f"{num:.2f}"
    except (ValueError, TypeError):
        value = raw_value
    display = f"{value}{unit}" if value else "n/a"
    return DataMetric(
        label=label, value=display, as_of=as_of,
        source=Source(url=_series_url(series_id), title=label,
                      publisher="FRED (St. Louis Fed)", published=as_of),
    )


def fetch_mortgage30us(transport: Optional[Callable] = None,
                       api_key: Optional[str] = None) -> DataMetric:
    return fetch_series(config.FRED_MORTGAGE_SERIES, "30-yr fixed mortgage",
                        unit="%", transport=transport, api_key=api_key)
