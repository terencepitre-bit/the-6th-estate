"""Shared test builders that produce a fully-valid demo Edition in memory."""
from __future__ import annotations

from sixth_estate.build import (assemble_edition, build_money_box,
                                build_sports_box, build_the_number,
                                build_scoreboard_weather_box, build_this_day)
from sixth_estate.schema import (Briefing, Closer, DataMetric, QuickHit,
                                 Receipt, Source, VoiceBlock)


def S(url, publisher="Pub", free=True):
    return Source(url=url, publisher=publisher, free_access=free)


def _body(n_words: int) -> str:
    return " ".join(["word"] * n_words)


def valid_briefings():
    return [
        Briefing(lane="World / US lead", headline="Lead headline demo",
                 body=_body(66),
                 sources=[S("https://www.congress.gov/bill/119th-congress/senate-bill/1/text"),
                          S("https://www.gao.gov/products/gao-24-106789")]),
        Briefing(lane="Money & Markets", headline="Markets headline demo",
                 body=_body(70), why_it_matters="It affects household budgets.",
                 sources=[S("https://fred.stlouisfed.org/series/MORTGAGE30US"),
                          S("https://home.treasury.gov/resource-center/data.html")]),
        Briefing(lane="Business", headline="Policy headline demo",
                 body=_body(64),
                 sources=[S("https://www.federalregister.gov/documents/2026/07/18/2026-1/rule")]),
        Briefing(lane="Science", headline="Science headline demo",
                 body=_body(60),
                 sources=[S("https://www.nejm.org/doi/full/10.1056/NEJMoa2400001")]),
    ]


def valid_quick_hits():
    return [
        QuickHit(text="A concise factual quick hit under the limit here.",
                 source=S("https://www.census.gov/construction/nrs/current/index.html")),
        QuickHit(text="Another concise factual quick hit within the word cap.",
                 source=S("https://www2.ed.gov/documents/press-releases/2026-07-15-civics.pdf")),
        QuickHit(text="Third concise factual quick hit, still short.",
                 source=S("https://www.loc.gov/item/2026655001/")),
        QuickHit(text="Fourth concise factual quick hit, brief.",
                 source=S("https://www.mlb.com/news/demo-clinch-2026-07-19")),
        QuickHit(text="Fifth concise factual quick hit, done.",
                 source=S("https://www.federalreserve.gov/newsevents/pressreleases/monetary20260715a.htm")),
        QuickHit(text="Sixth concise factual quick hit, extra.",
                 source=S("https://www.usa.gov/libraries-and-archives")),
    ]


def valid_data_boxes():
    money = build_money_box(
        equities=[DataMetric("S&P 500", "5,432", S("https://fred.stlouisfed.org/series/SP500"), "2026-07-19")],
        mortgage=DataMetric("30-yr", "6.6%", S("https://fred.stlouisfed.org/series/MORTGAGE30US"), "2026-07-17"),
    )
    sports = build_sports_box(
        scores=[DataMetric("NYY 5, BOS 3", "Final",
                           S("https://www.espn.com/mlb/scoreboard"), "2026-07-20")],
    )
    return [money, sports]


def valid_voice_blocks():
    this_day = build_this_day(VoiceBlock(kind="this_day", title="This Day",
                                         text="1969: demo event.", as_of="2026-07-20",
                                         source=S("https://en.wikipedia.org/wiki/July_20")))
    return [this_day]


def valid_receipt():
    return Receipt(
        title="Federal Register: Data-Broker Disclosure Rule",
        description="Final rule requiring data brokers to disclose categories of personal information sold.",
        source=S("https://www.federalregister.gov/documents/2026/07/18/2026-15321/data-broker-disclosure-rule"),
    )


def valid_closer():
    return Closer(kind="quote", factual=True, text="A sourced demo quote.",
                  attribution="Someone",
                  source=S("https://supreme.justia.com/cases/federal/us/403/713/"))


def valid_edition(date="2026-07-20"):
    return assemble_edition(date, valid_briefings(), valid_quick_hits(),
                            valid_data_boxes(), valid_voice_blocks(), valid_closer(),
                            receipt=valid_receipt(), demo=True)
