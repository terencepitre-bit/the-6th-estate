"""BLS adapter — CPI (CUUR0000SA0). Public series work without a key; BLS_API_KEY
raises the rate limit if provided (never logged). `transport` injectable for tests.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source

_CPI_PAGE = "https://www.bls.gov/cpi/"


def fetch_cpi(transport: Optional[Callable] = None,
              api_key: Optional[str] = None) -> DataMetric:
    series = config.BLS_CPI_SERIES
    api_key = api_key if api_key is not None else config.BLS_API_KEY
    if transport is not None:
        data = transport(series)
    else:
        url = f"{config.BLS_API_BASE}/timeseries/data/{series}"
        if api_key:
            url += f"?registrationkey={api_key}"
        data = get_json(url)
    result = (data.get("Results", {}) or {}).get("series", [{}])[0]
    rows = result.get("data", []) or [{}]
    latest = rows[0]
    value = latest.get("value", "")
    period = f"{latest.get('periodName', '')} {latest.get('year', '')}".strip()
    return DataMetric(
        label="CPI-U (all items)", value=value, as_of=period,
        source=Source(url=f"{_CPI_PAGE}#{series}", title="Consumer Price Index",
                      publisher="Bureau of Labor Statistics", published=period),
    )
