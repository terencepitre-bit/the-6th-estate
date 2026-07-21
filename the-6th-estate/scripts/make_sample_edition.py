#!/usr/bin/env python3
"""Generate a clearly-labeled DEMO edition (fixture data, not real current news).

Writes fixtures/sample_edition.json and editions/<date>.json. All sources point to
real, stable, direct documents so the direct-source validator passes; the prose is
fictional/illustrative and marked demo=True. Freshness is disabled for demos.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sixth_estate import config  # noqa: E402
from sixth_estate.build import (assemble_edition, build_money_box,  # noqa: E402
                                build_scoreboard_weather_box, build_the_number,
                                build_this_day)
from sixth_estate.schema import (Briefing, Closer, DataMetric, QuickHit,  # noqa: E402
                                 Source, VoiceBlock)
from sixth_estate.validation import validate_edition  # noqa: E402

DATE = "2026-07-20"


def S(url, publisher, title="", free=True):
    return Source(url=url, publisher=publisher, title=title, free_access=free)


def briefings():
    return [
        Briefing(
            lane="World / US lead",
            headline="DEMO: Coastal states finalize a shared wildfire-response compact",
            # 68 words
            body=("In this fictional demo item, four coastal states signed a compact to "
                  "pool aircraft, crews, and satellite data during peak fire months. "
                  "Officials said the agreement standardizes mutual-aid billing and "
                  "creates one dispatch desk for cross-border blazes. Supporters expect "
                  "faster initial attack; skeptics note funding still depends on annual "
                  "legislative approval, which could slip if budgets tighten during a "
                  "prolonged and unusually severe drought season."),
            high_risk=False,
            sources=[S("https://www.congress.gov/bill/119th-congress/senate-bill/1234/text", "Congress.gov"),
                     S("https://www.gao.gov/products/gao-24-106789", "GAO")],
        ),
        Briefing(
            lane="Money & Markets",
            headline="DEMO: Long rates hold as mortgage costs stay near cycle highs",
            # 66 words
            body=("This illustrative demo briefing describes a quiet session in which the "
                  "ten-year yield barely moved and the thirty-year fixed mortgage held "
                  "near recent highs. Lenders reported steady demand for adjustable "
                  "products as buyers hunted for lower initial payments. Analysts in this "
                  "fictional scenario said rate relief likely waits on clearer inflation "
                  "data expected later in the quarter from federal statistical agencies."),
            why_it_matters=("Higher long rates keep monthly payments elevated, which could "
                            "cool home sales and squeeze household budgets."),
            sources=[S("https://fred.stlouisfed.org/series/MORTGAGE30US", "FRED"),
                     S("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView.html", "US Treasury")],
        ),
        Briefing(
            lane="Business / Public Policy",
            headline="DEMO: Regulator publishes final rule on data-broker disclosures",
            # 63 words
            body=("In this demo, a federal regulator finalized a rule requiring data "
                  "brokers to disclose the categories of personal information they sell "
                  "and to whom. Companies get twelve months to comply. Industry groups in "
                  "the fictional example warned of compliance costs, while consumer "
                  "advocates called the transparency overdue and said it could reshape how "
                  "the secondary data market operates across many sectors."),
            sources=[S("https://www.federalregister.gov/documents/2026/07/18/2026-15321/data-broker-disclosure-rule", "Federal Register")],
        ),
        Briefing(
            lane="Science / Tech / Health",
            headline="DEMO: Trial reports modest gains for a low-cost diagnostic tool",
            # 64 words
            body=("This fictional demo summarizes a peer-reviewed trial in which a low-cost "
                  "diagnostic tool matched a more expensive scanner for a common condition "
                  "in most cases. Authors cautioned the study was mid-sized and single "
                  "region, so results could differ elsewhere. If replicated, the approach "
                  "could widen access in clinics that cannot afford larger machines, the "
                  "demo researchers noted in their published conclusions."),
            sources=[S("https://www.nejm.org/doi/full/10.1056/NEJMoa2400001", "NEJM")],
        ),
    ]


def quick_hits():
    return [
        QuickHit(lane="Real Estate",
                 text="DEMO: New-home sales edged up last month as builders trimmed prices to move inventory, a fictional release said.",
                 source=S("https://www.census.gov/construction/nrs/current/index.html", "US Census Bureau")),
        QuickHit(lane="Education",
                 text="DEMO: A state board approved a revised civics standard for high schools, effective next fall in this example.",
                 source=S("https://www2.ed.gov/documents/press-releases/2026-07-15-civics.pdf", "Dept. of Education")),
        QuickHit(lane="Culture",
                 text="DEMO: A restored silent film premiered at a national archive screening, drawing a sold-out demo crowd.",
                 source=S("https://www.loc.gov/item/2026655001/", "Library of Congress")),
        QuickHit(lane="Sports",
                 text="DEMO: The home side clinched a playoff berth with a late run in this illustrative fictional recap.",
                 source=S("https://www.mlb.com/news/demo-clinch-2026-07-19", "MLB.com")),
        QuickHit(lane="Et Cetera",
                 text="DEMO: A city library extended weekend hours after a pilot showed higher evening usage, per a fictional note.",
                 source=S("https://www.usa.gov/libraries-and-archives", "USA.gov")),
    ]


def data_boxes():
    money = build_money_box(
        equities=[
            DataMetric("S&P 500", "5,432.10 (demo)", S("https://fred.stlouisfed.org/series/SP500", "FRED"), "2026-07-19"),
            DataMetric("Dow", "39,876.00 (demo)", S("https://fred.stlouisfed.org/series/DJIA", "FRED"), "2026-07-19"),
            DataMetric("Nasdaq", "17,210.00 (demo)", S("https://fred.stlouisfed.org/series/NASDAQCOM", "FRED"), "2026-07-19"),
        ],
        treasury=DataMetric("10-yr Treasury", "4.21% (demo)", S("https://fred.stlouisfed.org/series/DGS10", "FRED"), "2026-07-19"),
        mortgage=DataMetric("30-yr fixed mortgage", "6.60% (demo)", S("https://fred.stlouisfed.org/series/MORTGAGE30US", "FRED"), "2026-07-17"),
        crypto=[
            DataMetric("BTC", "$61,250 (demo)", S("https://www.coingecko.com/en/coins/bitcoin", "CoinGecko"), "2026-07-20 12:00 UTC"),
            DataMetric("ETH", "$3,180 (demo)", S("https://www.coingecko.com/en/coins/ethereum", "CoinGecko"), "2026-07-20 12:00 UTC"),
        ],
        cpi=DataMetric("CPI-U (all items)", "+0.2% m/m (demo)", S("https://www.bls.gov/cpi/#CUUR0000SA0", "BLS"), "June 2026"),
    )
    scoreboard = build_scoreboard_weather_box(
        scores=[
            DataMetric("Home 5, Visitors 3 (demo)", "Final", S("https://www.mlb.com/gameday/demo-2026-07-19", "MLB.com"), "2026-07-19"),
            DataMetric("City 108, Rivals 101 (demo)", "Final", S("https://www.nba.com/game/demo-2026-07-19", "NBA.com"), "2026-07-19"),
        ],
        weather=[
            DataMetric("Today", "88°F — Sunny (demo)", S("https://api.weather.gov/gridpoints/LWX/96,70/forecast", "weather.gov"), "2026-07-20"),
            DataMetric("Tomorrow", "84°F — Scattered storms (demo)", S("https://api.weather.gov/gridpoints/LWX/96,70/forecast", "weather.gov"), "2026-07-21"),
            DataMetric("Wednesday", "80°F — Cloudy (demo)", S("https://api.weather.gov/gridpoints/LWX/96,70/forecast", "weather.gov"), "2026-07-22"),
        ],
    )
    return [money, scoreboard]


def voice_blocks():
    this_day = build_this_day(VoiceBlock(
        kind="this_day", title="This Day",
        text="1969 (demo context): a milestone anniversary noted for illustration only.",
        as_of=DATE,
        source=S("https://en.wikipedia.org/wiki/July_20", "Wikipedia"),
    ))
    the_number = build_the_number(
        DataMetric("30-yr fixed mortgage", "6.60% (demo)",
                   S("https://fred.stlouisfed.org/series/MORTGAGE30US", "FRED"), "2026-07-17"),
        framing="6.60% — the demo 30-year fixed mortgage rate this week (illustrative).",
    )
    return [this_day, the_number]


def closer():
    return Closer(
        kind="quote", factual=True,
        text="DEMO: \"The press was protected so that it could bare the secrets of government and inform the people.\"",
        attribution="Justice Hugo Black, New York Times Co. v. United States (illustrative citation)",
        source=S("https://supreme.justia.com/cases/federal/us/403/713/", "Justia"),
    )


def main():
    config.ensure_dirs()
    ed = assemble_edition(
        DATE, briefings(), quick_hits(), data_boxes(), voice_blocks(), closer(),
        demo=True, extra_meta={"date_readable": "Monday, July 20, 2026",
                               "label": "DEMO / FIXTURE EDITION — not real current news"},
    )
    result = validate_edition(ed, freshness_days=0)
    ed.save(config.FIXTURES_DIR / "sample_edition.json")
    ed.save(config.EDITIONS_DIR / f"{DATE}.json")
    print("Sample edition:", result.summary())
    for f in result.findings:
        print(f"  [{f.level}] {f.item}: {f.message}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
