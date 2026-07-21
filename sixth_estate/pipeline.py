"""Live pipeline: discover -> write -> fetch data -> assemble a complete edition.

New flexible structure:
  - Briefings: 4-6 (60-75 words, impact-focused)
  - Quick Hits: 5-9 (<=25 words)
  - Total articles: 10-15
  - Money Box: 1
  - Sports Box: 1 (MLB/NBA/NFL from ESPN)
  - This Day: 1 voice block
  - Receipt: 0-1 (primary-source doc, free-access only)
  - Closer: 1
  - NO weather, NO The Number

Design rules:
  - RSS-first, Brave only as a bounded fallback.
  - Strict free-access: never use paywalled sources.
  - Fail safe: missing sections stay empty, edition drops below floor.
  - Never fabricate content.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timezone
from typing import Optional

from . import config
from .build import (assemble_edition, build_money_box, build_sports_box,
                    build_this_day)
from .data.bls import fetch_cpi
from .data.coingecko import fetch_crypto
from .data.fred import fetch_series
from .data.sports import SportsDisabled, fetch_scores
from .data.wikipedia import fetch_on_this_day
from .discovery.brave import BraveCapExceeded, BraveClient, BraveDisabled
from .discovery.candidate import Candidate
from .discovery.rss import discover_rss
from .logging_util import EditionLogger
from .schema import (Briefing, Closer, DataMetric, Edition, QuickHit, Receipt,
                     Source, VoiceBlock)
from .writer.claude import ClaudeWriter, WriterBudgetExceeded, WriterDisabled

# Lane search queries for Brave fallback.
_LANE_QUERIES = {
    0: "breaking news today",
    1: "stock market today financial news",
    2: "business policy regulation news today",
    3: "science technology health news today",
    4: "economy jobs housing news today",
    5: "energy environment climate news today",
}

# Government/primary-source RSS feeds for receipts.
_RECEIPT_FEEDS = [
    "https://www.federalregister.gov/documents/search.atom?conditions%5Btype%5D=RULE",
    "https://www.gao.gov/rss/reports.xml",
]

# Primary-source domains that qualify as receipt material.
_RECEIPT_DOMAINS = {
    "federalregister.gov", "congress.gov", "gao.gov", "whitehouse.gov",
    "sec.gov", "supremecourt.gov", "uscourts.gov", "treasury.gov",
    "bls.gov", "census.gov", "cbo.gov", "oversight.gov",
    "justice.gov", "ed.gov", "hhs.gov", "epa.gov", "fda.gov",
    "ftc.gov", "fcc.gov", "osha.gov", "nlrb.gov",
}


def _classify_lane(cand: Candidate) -> int:
    """Rough lane assignment based on keywords in title/summary."""
    text = f"{cand.title} {cand.summary}".lower()
    money_kw = {"market", "stock", "dow", "nasdaq", "fed", "rate", "treasury",
                "inflation", "gdp", "economy", "economic", "bank", "mortgage",
                "yield", "bond", "investor", "earnings", "revenue", "profit"}
    science_kw = {"study", "research", "trial", "health", "disease", "climate",
                  "space", "nasa", "fda", "vaccine", "cancer", "drug", "ai",
                  "artificial intelligence", "tech", "technology", "robot"}
    business_kw = {"regulation", "policy", "antitrust", "ftc", "sec", "doj",
                   "congress", "legislation", "bill", "law", "court", "ruling",
                   "merger", "acquisition", "ceo", "company", "corporate"}
    if any(kw in text for kw in money_kw):
        return 1
    if any(kw in text for kw in science_kw):
        return 3
    if any(kw in text for kw in business_kw):
        return 2
    return 0  # default: lead


def _pick_candidates(candidates: list[Candidate]) -> dict[int, list[Candidate]]:
    buckets: dict[int, list[Candidate]] = {i: [] for i in range(6)}
    for c in candidates:
        lane = _classify_lane(c)
        buckets[lane].append(c)
    return buckets


def _build_briefings(writer: ClaudeWriter, candidates: list[Candidate],
                     brave: Optional[BraveClient], log: EditionLogger
                     ) -> list[Briefing]:
    """Produce 4-6 briefings from discovered candidates."""
    buckets = _pick_candidates(candidates)
    lanes = config.BRIEFING_LANES
    briefings: list[Briefing] = []

    # Try up to 6 lanes
    for idx in range(config.N_BRIEFINGS_MAX):
        if len(briefings) >= config.N_BRIEFINGS_MAX:
            break
        lane_name = lanes[idx] if idx < len(lanes) else f"General {idx}"
        pool = buckets.get(idx, [])

        # Brave fallback if a lane is empty
        if not pool and brave:
            query = _LANE_QUERIES.get(idx, "news today")
            try:
                pool = brave.search(query, count=3)
                log.info("brave_fallback", lane=idx, query=query, results=len(pool))
            except (BraveDisabled, BraveCapExceeded) as e:
                log.warning("brave_unavailable", lane=idx, error=str(e)[:80])

        if not pool:
            # Optional lanes (4+) can be empty
            if idx >= config.N_BRIEFINGS_MIN:
                continue
            log.warning("lane_empty", lane=idx, name=lane_name)
            continue

        for cand in pool[:3]:
            try:
                b = writer.write_briefing(cand, lane=lane_name)
            except (WriterDisabled, WriterBudgetExceeded):
                log.warning("writer_stopped", lane=idx)
                break
            if b:
                if idx in config.BRIEFING_TWO_SOURCE_INDICES and len(pool) > 1:
                    alt = [c for c in pool if c.url != cand.url]
                    if alt:
                        b.sources.append(Source(url=alt[0].url, title=alt[0].title,
                                                publisher=alt[0].publisher,
                                                published=alt[0].published))
                briefings.append(b)
                break

    return briefings


def _build_quick_hits(writer: ClaudeWriter, candidates: list[Candidate],
                      used_urls: set[str], brave: Optional[BraveClient],
                      target: int, log: EditionLogger) -> list[QuickHit]:
    """Produce quick hits to reach the article total target."""
    remaining = [c for c in candidates if c.url not in used_urls]
    random.shuffle(remaining)

    hits: list[QuickHit] = []
    tried = 0
    for cand in remaining:
        if len(hits) >= target:
            break
        tried += 1
        if tried > 20:
            break
        try:
            qh = writer.write_quick_hit(cand)
        except (WriterDisabled, WriterBudgetExceeded):
            break
        if qh:
            hits.append(qh)
            used_urls.add(cand.url)

    # Brave fallback for missing quick hits
    if len(hits) < config.N_QUICK_HITS_MIN and brave:
        _QH_QUERIES = [
            "real estate housing market news",
            "education schools policy news",
            "culture arts entertainment today",
            "interesting news today",
        ]
        for query in _QH_QUERIES:
            if len(hits) >= config.N_QUICK_HITS_MIN:
                break
            try:
                extras = brave.search(query, count=2)
            except (BraveDisabled, BraveCapExceeded):
                break
            for cand in extras:
                if cand.url in used_urls:
                    continue
                try:
                    qh = writer.write_quick_hit(cand)
                except (WriterDisabled, WriterBudgetExceeded):
                    break
                if qh:
                    hits.append(qh)
                    used_urls.add(cand.url)
                    break

    return hits


def _build_data_boxes(log: EditionLogger) -> list[DataMetric | None]:
    """Fetch live data. Returns (money_box, sports_box)."""
    from .build import build_money_box, build_sports_box
    from .schema import DataBox

    # --- Money Box ---
    equities: list[DataMetric] = []
    treasury = mortgage = cpi = None
    crypto: list[DataMetric] = []

    for series_id, label in [("SP500", "S&P 500"), ("DJIA", "Dow"),
                              ("NASDAQCOM", "Nasdaq")]:
        try:
            equities.append(fetch_series(series_id, label))
        except Exception as e:
            log.warning("fred_equity_failed", series=series_id, error=str(e)[:80])

    try:
        treasury = fetch_series("DGS10", "10-yr Treasury", unit="%")
    except Exception as e:
        log.warning("fred_treasury_failed", error=str(e)[:80])

    try:
        mortgage = fetch_series(config.FRED_MORTGAGE_SERIES,
                                "30-yr fixed mortgage", unit="%")
    except Exception as e:
        log.warning("fred_mortgage_failed", error=str(e)[:80])

    try:
        crypto = fetch_crypto()
    except Exception as e:
        log.warning("crypto_failed", error=str(e)[:80])

    try:
        cpi = fetch_cpi()
    except Exception as e:
        log.warning("cpi_failed", error=str(e)[:80])

    money = build_money_box(equities=equities, treasury=treasury,
                            mortgage=mortgage, crypto=crypto, cpi=cpi)

    # --- Sports Box ---
    scores: list[DataMetric] = []
    try:
        scores = fetch_scores()
    except (SportsDisabled, Exception) as e:
        log.warning("sports_failed", error=str(e)[:80])

    sports = build_sports_box(scores=scores)

    return [money, sports]


def _find_receipt(candidates: list[Candidate], used_urls: set[str],
                  log: EditionLogger) -> Optional[Receipt]:
    """Look for a primary-source document among candidates."""
    from urllib.parse import urlparse
    for c in candidates:
        if c.url in used_urls:
            continue
        try:
            host = urlparse(c.url).netloc.lower()
        except Exception:
            continue
        # Check if the source domain is a known primary-source publisher
        if any(d in host for d in _RECEIPT_DOMAINS):
            log.info("receipt_found", url=c.url, publisher=c.publisher)
            return Receipt(
                title=c.title,
                description=c.summary[:200] if c.summary else c.title,
                source=Source(url=c.url, title=c.title,
                              publisher=c.publisher or host,
                              published=c.published, free_access=True),
            )
    return None


def _build_voice_blocks(log: EditionLogger) -> list[VoiceBlock]:
    """Build This Day voice block only (The Number retired)."""
    blocks: list[VoiceBlock] = []
    try:
        td = fetch_on_this_day(on=date.today())
        blocks.append(build_this_day(td))
    except Exception as e:
        log.warning("this_day_failed", error=str(e)[:80])
    return blocks


def _build_closer(log: EditionLogger) -> Optional[Closer]:
    """Build a closer from curated public-domain quotes."""
    _QUOTES = [
        ("The press was protected so that it could bare the secrets of "
         "government and inform the people.",
         "Justice Hugo Black, New York Times Co. v. United States (1971)",
         "https://supreme.justia.com/cases/federal/us/403/713/"),
        ("A popular government without popular information, or the means of "
         "acquiring it, is but a prologue to a farce or a tragedy, or perhaps both.",
         "James Madison, letter to W.T. Barry (1822)",
         "https://founders.archives.gov/documents/Madison/04-02-02-0480"),
        ("The only security of all is in a free press.",
         "Thomas Jefferson, letter to Lafayette (1823)",
         "https://founders.archives.gov/documents/Jefferson/98-01-02-3837"),
        ("Let the people know the facts, and the country will be safe.",
         "Abraham Lincoln (attributed)",
         "https://www.loc.gov/collections/abraham-lincoln-papers/about-this-collection/"),
        ("Knowledge will forever govern ignorance; and a people who mean to "
         "be their own governors must arm themselves with the power which "
         "knowledge gives.",
         "James Madison, letter to W.T. Barry (1822)",
         "https://founders.archives.gov/documents/Madison/04-02-02-0480"),
    ]
    text, attribution, url = random.choice(_QUOTES)
    return Closer(
        kind="quote", factual=True,
        text=f'"{text}"',
        attribution=attribution,
        source=Source(url=url, title=attribution, publisher="Public record"),
    )


def run_pipeline(edition_date: Optional[str] = None,
                 log: Optional[EditionLogger] = None) -> Edition:
    """Execute the full daily pipeline and return an assembled Edition."""
    edition_date = edition_date or config.today_et()
    log = log or EditionLogger(edition_date)
    log.info("pipeline_start", date=edition_date)

    # 1. Discover candidates
    print(f"  [1/7] Discovering RSS candidates...")
    try:
        candidates = discover_rss(logger=log)
    except Exception as e:
        print(f"  ERROR in RSS discovery: {e}")
        candidates = []
    print(f"  Found {len(candidates)} RSS candidates.")
    log.info("discovery_done", rss_candidates=len(candidates))

    writer = ClaudeWriter(logger=log)
    print(f"  Claude writer: model={config.GEMINI_MODEL_BRIEFINGS}, "
          f"budget={config.MODEL_CALL_LIMIT} calls")
    brave: Optional[BraveClient] = None
    if config.BRAVE_SEARCH_ENABLED and config.BRAVE_API_KEY:
        brave = BraveClient(logger=log)
        print(f"  Brave search: enabled")

    # 2. Briefings (4-6)
    print(f"  [2/7] Writing briefings...")
    try:
        briefings = _build_briefings(writer, candidates, brave, log)
    except Exception as e:
        print(f"  ERROR in briefings: {e}")
        briefings = []
    print(f"  Wrote {len(briefings)} briefings ({writer.calls_used} Claude calls used).")
    log.info("briefings_done", count=len(briefings),
             writer_calls=writer.calls_used)

    used_urls = {s.url for b in briefings for s in b.sources}

    # 3. Quick hits — fill to reach 10-15 total articles
    print(f"  [3/7] Writing quick hits...")
    articles_so_far = len(briefings)
    qh_target = max(config.N_QUICK_HITS_MIN,
                    config.ARTICLE_TOTAL_MIN - articles_so_far)
    qh_target = min(qh_target, config.N_QUICK_HITS_MAX)
    try:
        quick_hits = _build_quick_hits(writer, candidates, used_urls, brave,
                                       qh_target, log)
    except Exception as e:
        print(f"  ERROR in quick hits: {e}")
        quick_hits = []
    print(f"  Wrote {len(quick_hits)} quick hits ({writer.calls_used} Claude calls used).")
    log.info("quick_hits_done", count=len(quick_hits),
             writer_calls=writer.calls_used)

    # 4. Data boxes (Money + Sports)
    print(f"  [4/7] Fetching data boxes...")
    try:
        data_boxes = _build_data_boxes(log)
    except Exception as e:
        print(f"  ERROR in data boxes: {e}")
        data_boxes = []
    print(f"  Built {len(data_boxes)} data boxes.")
    log.info("data_boxes_done", count=len(data_boxes))

    # 5. This Day voice block
    print(f"  [5/7] Building This Day...")
    voice_blocks = _build_voice_blocks(log)
    print(f"  Built {len(voice_blocks)} voice blocks.")
    log.info("voice_blocks_done", count=len(voice_blocks))

    # 6. Receipt (0-1, from primary-source candidates)
    print(f"  [6/7] Looking for receipt...")
    receipt = _find_receipt(candidates, used_urls, log)
    print(f"  Receipt: {'found' if receipt else 'none available'}.")

    # 7. Closer
    print(f"  [7/7] Building closer...")
    closer = _build_closer(log)

    # 8. Assemble
    ed = assemble_edition(
        edition_date, briefings, quick_hits, data_boxes, voice_blocks, closer,
        receipt=receipt,
        demo=False,
        extra_meta={
            "date_readable": datetime.now(config.ET).strftime("%A, %B %d, %Y"),
            "writer_calls": writer.calls_used,
            "brave_queries": brave.queries_used if brave else 0,
            "rss_candidates": len(candidates),
        },
    )

    total_articles = len(ed.briefings) + len(ed.quick_hits)
    print(f"  Summary: {len(ed.briefings)} briefings, {len(ed.quick_hits)} quick hits, "
          f"{len(ed.data_boxes)} data boxes, {len(ed.voice_blocks)} voice, "
          f"receipt={'yes' if receipt else 'no'}, closer={'yes' if closer else 'no'}")
    log.info("pipeline_done", briefings=len(ed.briefings),
             quick_hits=len(ed.quick_hits), total_articles=total_articles,
             receipt=bool(receipt))
    return ed
