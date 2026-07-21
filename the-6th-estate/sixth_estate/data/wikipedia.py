"""Wikipedia 'On This Day' adapter for the 'This Day' voice block.

Free Wikimedia feed API. `transport` injectable for tests. Returns a VoiceBlock
with a direct Wikipedia source link and the exact date as as-of.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from ..schema import Source, VoiceBlock


def fetch_on_this_day(on: Optional[date] = None,
                      transport: Optional[Callable] = None) -> VoiceBlock:
    on = on or date.today()
    mm, dd = f"{on.month:02d}", f"{on.day:02d}"
    if transport is not None:
        data = transport(mm, dd)
    else:
        url = f"{config.WIKIPEDIA_API_BASE}/events/{mm}/{dd}"
        data = get_json(url, headers={"User-Agent": "6E-bot/1.0", "Accept": "application/json"})
    events = data.get("events", []) or []
    if not events:
        return VoiceBlock(kind="this_day", title="This Day", text="", as_of=on.isoformat())
    ev = events[0]
    year = ev.get("year", "")
    text = ev.get("text", "")
    pages = ev.get("pages", []) or []
    link = ""
    if pages:
        link = ((pages[0].get("content_urls", {}) or {}).get("desktop", {}) or {}).get("page", "")
        link = link or pages[0].get("content_urls", {}).get("mobile", {}).get("page", "")
    return VoiceBlock(
        kind="this_day", title="This Day",
        text=f"{year}: {text}".strip(": "),
        as_of=on.isoformat(),
        source=Source(url=link or "https://en.wikipedia.org/wiki/Main_Page",
                      title=f"On this day — {mm}/{dd}", publisher="Wikipedia",
                      published=on.isoformat()),
    )
