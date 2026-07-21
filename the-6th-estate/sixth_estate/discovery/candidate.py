"""Normalized candidate model shared by every discovery source."""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import config


@dataclass
class Candidate:
    """A single discovered story candidate, normalized across RSS/Brave/PSE."""
    title: str
    url: str
    summary: str = ""
    published: str = ""       # ISO date if known
    publisher: str = ""
    source_kind: str = "rss"  # "rss" | "brave" | "google_pse"
    tags: list[str] = field(default_factory=list)

    @property
    def is_direct(self) -> bool:
        return not config.is_generic_source_url(self.url)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "url": self.url, "summary": self.summary,
            "published": self.published, "publisher": self.publisher,
            "source_kind": self.source_kind, "tags": list(self.tags),
        }


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    """Drop duplicate URLs (order-preserving) and non-direct links."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        if not c.is_direct:
            continue
        key = c.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
