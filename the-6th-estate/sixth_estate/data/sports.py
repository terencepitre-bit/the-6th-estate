"""Sports-scores provider abstraction for the Scoreboard data box.

IMPORTANT (permitted-use caveat): ESPN's hidden endpoints are not an officially
documented/licensed public API. Confirm permitted use before enabling, and prefer
official league feeds (MLB/NBA/NFL) where licensing allows. This module ships
DISABLED by default (config.SPORTS_PROVIDER == "") and only calls out when the
operator explicitly opts in. `transport` is injectable for tests.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source


class SportsDisabled(RuntimeError):
    pass


def fetch_scores(league: str = "mlb", transport: Optional[Callable] = None,
                 provider: Optional[str] = None) -> list[DataMetric]:
    """Return recent final scores as DataMetrics. Raises SportsDisabled unless a
    provider is configured or a transport is injected (tests)."""
    provider = provider if provider is not None else config.SPORTS_PROVIDER
    if transport is None and not provider:
        raise SportsDisabled(
            "No sports provider configured. Set SIXTHE_SPORTS_PROVIDER after "
            "confirming permitted use; prefer official league feeds."
        )
    if transport is not None:
        data = transport(league)
    else:
        # Provider-specific URL construction left to the operator's configured base.
        url = f"{config.SPORTS_API_BASE}/{league}/scoreboard"
        data = get_json(url)
    events = data.get("events", []) or []
    out: list[DataMetric] = []
    for ev in events:
        name = ev.get("name", "") or ev.get("shortName", "")
        status = (ev.get("status", {}) or {}).get("type", {}).get("description", "")
        link = ev.get("link", "") or ev.get("url", "")
        out.append(DataMetric(
            label=name, value=status or "final",
            as_of=ev.get("date", "")[:10],
            source=Source(url=link, title=name, publisher=provider or "league feed",
                          published=ev.get("date", "")[:10]),
        ))
    return out
