"""Sports-scores adapter — MLB/NBA/NFL via ESPN public scoreboard endpoints.

ESPN's public scoreboard endpoints are widely used but NOT an officially
documented public API. Confirm permitted use before relying on them. Prefer
official league feeds if available.

`transport` is injectable so tests exercise parsing with zero network calls.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import DataMetric, Source


class SportsDisabled(RuntimeError):
    pass


# ESPN sport paths by league key.
_ESPN_PATHS = {
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "nfl": "football/nfl",
    "nhl": "hockey/nhl",
    "wnba": "basketball/wnba",
}


def _espn_scoreboard_url(league: str) -> str:
    path = _ESPN_PATHS.get(league, league)
    return f"{config.SPORTS_API_BASE}/{path}/scoreboard"


def _parse_espn_event(ev: dict, league: str) -> Optional[DataMetric]:
    """Parse one ESPN event into a DataMetric, or None if not final."""
    status = (ev.get("status", {}) or {}).get("type", {})
    state = status.get("state", "")
    # Only include completed games
    if state not in ("post",):
        return None

    competitors = (ev.get("competitions", [{}])[0].get("competitors", []))
    if len(competitors) < 2:
        return None

    # Build "Team1 Score1, Team2 Score2" label
    parts = []
    for c in competitors:
        name = c.get("team", {}).get("abbreviation", "???")
        score = c.get("score", "?")
        winner = c.get("winner", False)
        prefix = "" if not winner else ""
        parts.append(f"{prefix}{name} {score}")

    label = " — ".join(parts)
    detail = status.get("shortDetail", "Final")
    link = ""
    for lnk in ev.get("links", []):
        if lnk.get("text") == "Gamecast" or "gameId" in lnk.get("href", ""):
            link = lnk.get("href", "")
            break
    if not link:
        link = f"https://www.espn.com/{_ESPN_PATHS.get(league, league)}/scoreboard"

    return DataMetric(
        label=label, value=detail,
        as_of=ev.get("date", "")[:10],
        source=Source(url=link, title=label,
                      publisher=f"ESPN ({league.upper()})",
                      published=ev.get("date", "")[:10]),
    )


def fetch_scores(leagues: Optional[list[str]] = None,
                 transport: Optional[Callable] = None,
                 max_per_league: int = 3) -> list[DataMetric]:
    """Fetch recent final scores across configured leagues."""
    leagues = leagues if leagues is not None else config.SPORTS_LEAGUES
    provider = config.SPORTS_PROVIDER

    if transport is None and not provider:
        raise SportsDisabled(
            "No sports provider configured. Set SIXTHE_SPORTS_PROVIDER."
        )

    out: list[DataMetric] = []
    for league in leagues:
        try:
            if transport is not None:
                data = transport(league)
            else:
                url = _espn_scoreboard_url(league)
                data = get_json(url, headers={
                    "User-Agent": "6E-bot/1.0",
                    "Accept": "application/json"})
            events = data.get("events", []) or []
            count = 0
            for ev in events:
                if count >= max_per_league:
                    break
                metric = _parse_espn_event(ev, league)
                if metric:
                    out.append(metric)
                    count += 1
        except SportsDisabled:
            raise
        except Exception:
            continue  # a bad league must not kill the whole box

    return out
