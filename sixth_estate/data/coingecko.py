"""CoinGecko adapter — BTC/ETH spot prices (free public API, no key required).
`transport` injectable for tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source

_COIN_PAGE = {"bitcoin": "https://www.coingecko.com/en/coins/bitcoin",
              "ethereum": "https://www.coingecko.com/en/coins/ethereum"}
_LABEL = {"bitcoin": "BTC", "ethereum": "ETH"}


def fetch_crypto(transport: Optional[Callable] = None) -> list[DataMetric]:
    ids = "bitcoin,ethereum"
    if transport is not None:
        data = transport(ids)
    else:
        url = f"{config.COINGECKO_API_BASE}/simple/price?ids={ids}&vs_currencies=usd"
        data = get_json(url)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: list[DataMetric] = []
    for coin in ("bitcoin", "ethereum"):
        price = (data.get(coin) or {}).get("usd")
        display = f"${price:,.0f}" if isinstance(price, (int, float)) else "n/a"
        out.append(DataMetric(
            label=_LABEL[coin], value=display, as_of=as_of,
            source=Source(url=_COIN_PAGE[coin], title=f"{_LABEL[coin]} price",
                          publisher="CoinGecko", published=as_of),
        ))
    return out
