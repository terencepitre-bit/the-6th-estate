"""Google Programmable Search adapter — OPTIONAL backup interface, DISABLED by
default. Provided as an interface only; enable with SIXTHE_GOOGLE_PSE_ENABLED=1
plus GOOGLE_PSE_KEY and GOOGLE_PSE_CX. Never enabled automatically.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import config
from ..http_util import get_json
from .candidate import Candidate, dedupe


class GooglePSEDisabled(RuntimeError):
    pass


class GooglePSEClient:
    def __init__(self, api_key: Optional[str] = None, cx: Optional[str] = None,
                 transport: Optional[Callable] = None, logger=None):
        self.api_key = api_key if api_key is not None else config.GOOGLE_PSE_KEY
        self.cx = cx if cx is not None else config.GOOGLE_PSE_CX
        self.enabled = config.GOOGLE_PSE_ENABLED and bool(self.api_key and self.cx)
        self._transport = transport
        self.logger = logger

    def search(self, query: str, count: int = 5) -> list[Candidate]:
        if not self.enabled:
            raise GooglePSEDisabled("Google PSE is disabled or missing credentials")
        data = self._fetch(query, count)
        items = data.get("items", []) or []
        cands = [
            Candidate(title=i.get("title", ""), url=i.get("link", ""),
                      summary=i.get("snippet", ""), source_kind="google_pse")
            for i in items
        ]
        return dedupe(cands)

    def _fetch(self, query: str, count: int) -> dict:
        if self._transport:
            return self._transport(query, count)
        url = (f"{config.GOOGLE_PSE_BASE}?key={self.api_key}&cx={self.cx}"
               f"&q={query}&num={count}")
        return get_json(url)
