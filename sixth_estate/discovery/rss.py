"""RSS/Atom discovery using only the stdlib (xml.etree).

Free ($0) primary discovery. `fetch` is injectable so tests pass canned XML and
never hit the network.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable, Optional

from .. import config
from ..http_util import get_text
from .candidate import Candidate, dedupe

Fetcher = Callable[[str], str]

_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _text(el, tag) -> str:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    a = el.find(f"atom:{tag}", _NS)
    return a.text.strip() if a is not None and a.text else ""


def _atom_link(entry) -> str:
    link = entry.find("atom:link", _NS)
    if link is not None:
        return link.get("href", "").strip()
    return ""


def parse_feed(xml_text: str, publisher: str = "") -> list[Candidate]:
    out: list[Candidate] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    # RSS 2.0: channel/item
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        summary = _text(item, "description")
        pub = _text(item, "pubDate")
        if title and link:
            out.append(Candidate(title=title, url=link, summary=summary,
                                 published=pub, publisher=publisher, source_kind="rss"))
    # Atom: entry
    for entry in root.findall(".//atom:entry", _NS):
        title = _text(entry, "title")
        link = _atom_link(entry)
        summary = _text(entry, "summary")
        pub = _text(entry, "updated") or _text(entry, "published")
        if title and link:
            out.append(Candidate(title=title, url=link, summary=summary,
                                 published=pub, publisher=publisher, source_kind="rss"))
    return out


def discover_rss(feeds: Optional[list[str]] = None,
                 fetch: Optional[Fetcher] = None,
                 logger=None) -> list[Candidate]:
    """Read every configured feed, normalize, dedupe, drop non-direct links.

    `fetch(url)->xml` defaults to a live HTTP GET; inject a fake in tests.
    """
    feeds = feeds if feeds is not None else config._rss_feeds()
    fetch = fetch or get_text
    cands: list[Candidate] = []
    for url in feeds:
        try:
            xml_text = fetch(url)
        except Exception as e:  # a bad feed must not kill discovery
            if logger:
                logger.warning("rss_fetch_failed", feed=url, error=str(e)[:120])
            continue
        cands.extend(parse_feed(xml_text))
        if logger:
            logger.info("rss_read", feed=url)
    return dedupe(cands)
