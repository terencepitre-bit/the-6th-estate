"""Brave Search fallback client — used ONLY to fill missing sections, with a hard
per-day query cap. Disabled unless SIXTHE_BRAVE_ENABLED=1 and BRAVE_API_KEY set.

The API key is read from config (env) and sent as a header; it is never logged.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from .candidate import Candidate, dedupe


class BraveDisabled(RuntimeError):
    pass


class BraveCapExceeded(RuntimeError):
    pass


class BraveClient:
    def __init__(self, api_key: Optional[str] = None, daily_cap: Optional[int] = None,
                 transport: Optional[Callable] = None, logger=None):
        self.api_key = api_key if api_key is not None else config.BRAVE_API_KEY
        self.daily_cap = daily_cap if daily_cap is not None else config.BRAVE_DAILY_QUERY_CAP
        self.enabled = config.BRAVE_SEARCH_ENABLED and bool(self.api_key)
        self._transport = transport            # injectable for tests
        self._used = 0
        self.logger = logger

    @property
    def queries_used(self) -> int:
        return self._used

    def search(self, query: str, count: int = 5) -> list[Candidate]:
        if not self.enabled:
            raise BraveDisabled("Brave fallback is disabled or missing credentials")
        if self._used >= self.daily_cap:
            raise BraveCapExceeded(f"daily query cap {self.daily_cap} reached")
        self._used += 1
        if self.logger:
            self.logger.info("brave_query", n=self._used, cap=self.daily_cap)
        data = self._fetch(query, count)
        results = (data.get("web", {}) or {}).get("results", []) or []
        cands = [
            Candidate(title=r.get("title", ""), url=r.get("url", ""),
                      summary=r.get("description", ""), publisher=r.get("profile", {}).get("name", ""),
                      source_kind="brave")
            for r in results
        ]
        return dedupe(cands)

    def _fetch(self, query: str, count: int) -> dict:
        if self._transport:
            return self._transport(query, count)
        url = f"{config.BRAVE_API_BASE}?q={query}&count={count}"
        headers = {"Accept": "application/json", "X-Subscription-Token": self.api_key}
        return get_json(url, headers=headers)
