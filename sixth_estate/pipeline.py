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

import re
import random
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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
    4: "education schools university news today",
    5: "inspiring people achievement impact today",
    6: "real estate housing market news today",
    7: "arts culture entertainment news today",
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


# ── Interest scoring (heuristic, no model call) ─────────────────────────────
# Scores 1-5 based on signals that correlate with reader interest.
# This is deliberately cheap — runs on every candidate with no API calls.

# Words that signal concrete, high-impact stories readers care about.
_INTEREST_BOOST_WORDS = {
    # Action / consequence
    "bans", "banned", "launches", "launches", "raises", "cuts", "kills",
    "fires", "shuts", "blocks", "approves", "rejects", "suspends", "resigns",
    "arrests", "charges", "warns", "breaks", "surges", "crashes", "collapses",
    "reverses", "expands", "reveals", "confirms", "strikes", "record",
    # Scale / specificity
    "billion", "million", "trillion", "percent", "thousands", "hundreds",
    # People care about people
    "workers", "families", "parents", "children", "patients", "students",
    "veterans", "homeowners", "consumers", "employees",
    # Urgency
    "breaking", "emergency", "deadline", "crisis", "first", "historic",
    "unprecedented",
}

# Words that signal niche, procedural, or low-general-interest stories.
_INTEREST_PENALTY_WORDS = {
    "reclassified", "reclassification", "designation", "memorandum",
    "subcommittee", "appendix", "appendices", "docket", "solicitation",
    "rulemaking", "codified", "promulgated", "gazette", "registrar",
    "pursuant", "thereof", "herein", "addendum", "supersedes",
    "technical correction", "errata", "comment period",
}


def _score_interest(cand: Candidate) -> int:
    """Rate a candidate 1-5 for general-audience interest.

    Scoring rules:
      - Base score: 2 (publishable but unremarkable)
      - +1 if title contains a number, dollar amount, or percentage
      - +1 if title contains a high-interest action verb or scale word
      - +1 if title contains a proper noun (capitalized word not at start)
      - -1 if title/summary is heavy on bureaucratic/procedural language
      - Clamped to [1, 5]
    """
    title = cand.title or ""
    text = f"{title} {cand.summary or ''}".lower()
    words = set(re.findall(r"[a-z]+", text))

    score = 2  # base

    # Boost: contains a concrete number, dollar amount, or percentage
    if re.search(r"(\$[\d,.]+|\d+%|\b\d{2,}\b)", title):
        score += 1

    # Boost: high-interest action/scale words
    if words & _INTEREST_BOOST_WORDS:
        score += 1

    # Boost: proper noun beyond first word (signals a specific person/place/org)
    title_words = title.split()
    if len(title_words) > 1 and any(w[0].isupper() and w.isalpha() and len(w) > 1
                                     for w in title_words[1:]):
        score += 1

    # Penalty: bureaucratic/procedural language
    if words & _INTEREST_PENALTY_WORDS:
        score -= 1

    # Penalty: very short or empty summary (often a bare press release title)
    if len(cand.summary or "") < 30:
        score -= 1

    return max(1, min(5, score))


def _parse_pub_date(date_str: str) -> Optional[datetime]:
    """Best-effort parse of RSS pubDate / Atom updated fields.

    Handles RFC 2822 (RSS), ISO 8601 (Atom), and bare YYYY-MM-DD.
    Returns a timezone-aware datetime or None on failure.
    """
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    # RFC 2822 (standard RSS pubDate)
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    # ISO 8601 variants
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _is_fresh(cand: Candidate, max_age_hours: int) -> bool:
    """True if the candidate was published within max_age_hours, or if we
    can't parse the date (benefit of the doubt — don't discard unknowns)."""
    dt = _parse_pub_date(cand.published)
    if dt is None:
        return True  # unknown date — keep it rather than silently drop
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return dt >= cutoff


def _classify_lane(cand: Candidate) -> int:
    """Rough lane assignment based on keywords in title/summary.
    Lanes: 0=World/US, 1=Money, 2=Business/Policy, 3=Science/Tech/Health,
           4=Education, 5=Personal Excellence, 6=Real Estate, 7=Culture."""
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
    education_kw = {"school", "university", "college", "student", "teacher",
                    "education", "campus", "tuition", "graduate", "scholarship",
                    "curriculum", "classroom", "principal", "professor", "degree"}
    realestate_kw = {"housing", "real estate", "home sales", "rent", "mortgage rate",
                     "property", "homebuyer", "eviction", "zoning", "construction"}
    culture_kw = {"museum", "festival", "arts", "film", "book", "music", "theater",
                  "exhibition", "cultural", "literary", "award", "comedy", "concert"}
    if any(kw in text for kw in education_kw):
        return 4
    if any(kw in text for kw in realestate_kw):
        return 6
    if any(kw in text for kw in culture_kw):
        return 7
    if any(kw in text for kw in money_kw):
        return 1
    if any(kw in text for kw in science_kw):
        return 3
    if any(kw in text for kw in business_kw):
        return 2
    return 0  # default: lead


def _pick_candidates(candidates: list[Candidate]) -> dict[int, list[Candidate]]:
    buckets: dict[int, list[Candidate]] = {i: [] for i in range(len(config.BRIEFING_LANES))}
    for c in candidates:
        lane = _classify_lane(c)
        if lane not in buckets:
            buckets[lane] = []
        buckets[lane].append(c)
    return buckets


def _build_briefings(writer: ClaudeWriter, candidates: list[Candidate],
                     brave: Optional[BraveClient], log: EditionLogger
                     ) -> list[Briefing]:
    """Produce 4-6 briefings from discovered candidates.

    Core lanes (0-3: World/US, Money, Business/Policy, Science/Tech/Health)
    are attempted first and get Brave fallback. Optional lanes (4+: Education,
    Personal Excellence, Real Estate, Culture) fill remaining slots if available.
    """
    buckets = _pick_candidates(candidates)
    lanes = config.BRIEFING_LANES
    briefings: list[Briefing] = []

    # Core lanes first (0-3), then optional lanes (4+)
    core_count = min(4, len(lanes))
    lane_order = list(range(core_count)) + list(range(core_count, len(lanes)))

    for idx in lane_order:
        if len(briefings) >= config.N_BRIEFINGS_MAX:
            break
        lane_name = lanes[idx] if idx < len(lanes) else f"General {idx}"
        pool = buckets.get(idx, [])

        # Brave fallback only for core lanes (0-3)
        if not pool and brave and idx < core_count:
            query = _LANE_QUERIES.get(idx, "news today")
            try:
                pool = brave.search(query, count=3)
                log.info("brave_fallback", lane=idx, query=query, results=len(pool))
            except (BraveDisabled, BraveCapExceeded) as e:
                log.warning("brave_unavailable", lane=idx, error=str(e)[:80])

        if not pool:
            # Core lanes (0-3) log a warning; optional lanes silently skip
            if idx < core_count:
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
    """Produce quick hits to reach the article total target.

    Pipeline: filter stale → score interest → sort by score within lanes →
    round-robin across lanes for diversity. This prevents government-heavy
    feeds from dominating AND ensures only interesting, fresh stories appear.
    """
    remaining = [c for c in candidates if c.url not in used_urls]

    # ── Filter 1: recency — drop stories older than max_age_hours ──
    max_age = config.QUICK_HIT_MAX_AGE_HOURS
    fresh = [c for c in remaining if _is_fresh(c, max_age)]
    stale_count = len(remaining) - len(fresh)
    if stale_count:
        log.info("quick_hits_stale_filtered", dropped=stale_count,
                 max_age_hours=max_age)
    remaining = fresh

    # ── Filter 2: interest scoring — drop below threshold, sort by score ──
    min_score = config.QUICK_HIT_MIN_INTEREST_SCORE
    scored = [(c, _score_interest(c)) for c in remaining]
    dropped_boring = sum(1 for _, s in scored if s < min_score)
    if dropped_boring:
        log.info("quick_hits_interest_filtered", dropped=dropped_boring,
                 min_score=min_score)
    scored = [(c, s) for c, s in scored if s >= min_score]

    # Bucket by lane, sorted by score (highest first) within each lane
    lane_pools: dict[int, list[Candidate]] = {}
    for c, score in scored:
        lane = _classify_lane(c)
        lane_pools.setdefault(lane, []).append((c, score))

    # Sort each lane by score descending, then light shuffle within same-score
    # tiers so equal-scoring stories aren't always in the same order
    for lane in lane_pools:
        pool = lane_pools[lane]
        pool.sort(key=lambda x: x[1], reverse=True)
        # Group by score tier and shuffle within each tier
        tier_start = 0
        while tier_start < len(pool):
            tier_score = pool[tier_start][1]
            tier_end = tier_start
            while tier_end < len(pool) and pool[tier_end][1] == tier_score:
                tier_end += 1
            tier = pool[tier_start:tier_end]
            random.shuffle(tier)
            pool[tier_start:tier_end] = tier
            tier_start = tier_end
        # Unwrap back to just candidates
        lane_pools[lane] = [c for c, _ in pool]

    # Round-robin: take one from each lane, repeat until target met
    ordered: list[Candidate] = []
    lane_indices = sorted(lane_pools.keys())
    cursors = {lane: 0 for lane in lane_indices}
    while len(ordered) < len(remaining):
        added_this_round = False
        for lane in lane_indices:
            pool = lane_pools[lane]
            cursor = cursors[lane]
            if cursor < len(pool):
                ordered.append(pool[cursor])
                cursors[lane] = cursor + 1
                added_this_round = True
        if not added_this_round:
            break

    hits: list[QuickHit] = []
    tried = 0
    for cand in ordered:
        if len(hits) >= target:
            break
        tried += 1
        if tried > 25:
            break
        try:
            qh = writer.write_quick_hit(cand)
        except (WriterDisabled, WriterBudgetExceeded):
            break
        if qh:
            hits.append(qh)
            used_urls.add(cand.url)

    # Brave fallback for missing quick hits — use diverse queries
    if len(hits) < config.N_QUICK_HITS_MIN and brave:
        _QH_QUERIES = [
            "education schools university news today",
            "real estate housing market news today",
            "arts culture entertainment news today",
            "inspiring achievement impact news today",
            "interesting unusual news today",
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


def _build_sports_quick_hits(writer: ClaudeWriter, log: EditionLogger
                              ) -> list[DataMetric]:
    """Discover up to 2 sports news stories and write them as editorial quick
    hits for the Sports Box. These are DataMetric objects with as_of='quick_hit'
    so the template renders them above the scores table."""
    from .discovery.rss import discover_rss
    from .schema import DataMetric, Source

    feeds = config._sports_rss_feeds()
    if not feeds:
        return []

    try:
        candidates = discover_rss(feeds=feeds, logger=log)
    except Exception as e:
        log.warning("sports_rss_failed", error=str(e)[:80])
        return []

    if not candidates:
        log.info("sports_rss_empty", feeds=len(feeds))
        return []

    log.info("sports_rss_candidates", count=len(candidates))

    hits: list[DataMetric] = []
    tried = 0
    for cand in candidates[:8]:  # try up to 8 to get 2
        if len(hits) >= config.SPORTS_QUICK_HITS_MAX:
            break
        tried += 1
        try:
            qh = writer.write_quick_hit(cand, lane="Sports")
        except (WriterDisabled, WriterBudgetExceeded):
            break
        except Exception:
            continue
        if qh and qh.text:
            hits.append(DataMetric(
                label=qh.text,
                value="",
                as_of="quick_hit",
                source=Source(url=cand.url, title=cand.title,
                              publisher=cand.publisher or "ESPN",
                              published=cand.published, free_access=True),
            ))
    log.info("sports_quick_hits_done", count=len(hits), tried=tried)
    return hits


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
    print(f"  Claude writer: model={config.CLAUDE_MODEL}, "
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
    print(f"  [4/8] Fetching data boxes...")
    try:
        data_boxes = _build_data_boxes(log)
    except Exception as e:
        print(f"  ERROR in data boxes: {e}")
        data_boxes = []
    print(f"  Built {len(data_boxes)} data boxes.")
    log.info("data_boxes_done", count=len(data_boxes))

    # 4b. Sports quick hits (up to 2 editorial items for the Sports Box)
    print(f"  [4b/8] Building sports quick hits...")
    try:
        sports_qh = _build_sports_quick_hits(writer, log)
    except Exception as e:
        print(f"  ERROR in sports quick hits: {e}")
        sports_qh = []
    if sports_qh:
        # Inject quick hits at the front of the Sports Box metrics
        for box in data_boxes:
            if box and box.kind == "sports":
                box.metrics = sports_qh + box.metrics
                break
    print(f"  Sports quick hits: {len(sports_qh)}.")

    # 5. This Day voice block
    print(f"  [5/8] Building This Day...")
    voice_blocks = _build_voice_blocks(log)
    print(f"  Built {len(voice_blocks)} voice blocks.")
    log.info("voice_blocks_done", count=len(voice_blocks))

    # 6. Receipt (0-1, from primary-source candidates)
    print(f"  [6/8] Looking for receipt...")
    receipt = _find_receipt(candidates, used_urls, log)
    print(f"  Receipt: {'found' if receipt else 'none available'}.")

    # 7. Closer
    print(f"  [7/8] Building closer...")
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
