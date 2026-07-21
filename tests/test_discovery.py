from sixth_estate.discovery import BraveClient, GooglePSEClient
from sixth_estate.discovery.brave import BraveDisabled
from sixth_estate.discovery.google_pse import GooglePSEDisabled
from sixth_estate.discovery.rss import discover_rss, parse_feed

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Demo</title>
  <item><title>Real deep story about the economy</title>
    <link>https://example.gov/press/2026/07/economy-report-12345</link>
    <description>Summary</description><pubDate>2026-07-20</pubDate></item>
  <item><title>Homepage link should be dropped</title>
    <link>https://example.com/</link><description>x</description></item>
</channel></rss>"""


def test_parse_feed_extracts_items():
    cands = parse_feed(RSS_SAMPLE)
    assert len(cands) == 2


def test_discover_rss_drops_generic_and_dedupes():
    def fake_fetch(url):
        return RSS_SAMPLE
    cands = discover_rss(feeds=["u1", "u2"], fetch=fake_fetch)
    # Both feeds return the same items; only the one direct URL survives, deduped.
    assert len(cands) == 1
    assert cands[0].url.endswith("economy-report-12345")


def test_discover_rss_survives_bad_feed():
    def boom(url):
        raise RuntimeError("network down")
    assert discover_rss(feeds=["x"], fetch=boom) == []


def test_brave_disabled_by_default():
    c = BraveClient(api_key="")  # no key -> disabled
    assert not c.enabled
    try:
        c.search("q")
        assert False, "should have raised"
    except BraveDisabled:
        pass


def test_brave_respects_cap_with_transport():
    calls = {"n": 0}

    def transport(q, count):
        calls["n"] += 1
        return {"web": {"results": [
            {"title": "Deep story", "url": "https://ex.gov/doc-98765", "description": "d"}]}}

    c = BraveClient(api_key="k", daily_cap=2, transport=transport)
    c.enabled = True  # simulate SIXTHE_BRAVE_ENABLED
    c.search("a"); c.search("b")
    from sixth_estate.discovery.brave import BraveCapExceeded
    try:
        c.search("c")
        assert False
    except BraveCapExceeded:
        pass
    assert c.queries_used == 2


def test_google_pse_disabled_by_default():
    c = GooglePSEClient(api_key="", cx="")
    assert not c.enabled
    try:
        c.search("q")
        assert False
    except GooglePSEDisabled:
        pass
