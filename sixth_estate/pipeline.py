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

import json
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


# ── Geography focus (heuristic, no model call) ──────────────────────────────
# The audience is US-based. Non-US stories are capped per section, not banned:
# a Japan earthquake or Spain wildfire can still lead World/US, but UK council
# news and magistrates-court items should not crowd out US coverage.

_NON_US_MARKERS = (
    "£", "€", " uk ", "u.k.", "britain", "british", "england", "scotland",
    "wales", "northern ireland", "london", "nhs", "downing street",
    "westminster", "parliament", "house of commons", "labour", "tory",
    "tories", "magistrates", "council tax", "ofsted", "hmrc", "bbc",
    "brexit", "starmer", "burnham", "farage", "sunak",
    " mp ", " mps ", "whitehall", "home office", "chancellor of the exchequer",
    "canada", "canadian", "ottawa", "trudeau", "australia", "australian",
    "canberra", "new zealand",
)

_US_MARKERS = (
    " us ", "u.s.", "united states", "america", "american", "washington",
    "congress", "senate", "white house", "federal", "biden", "trump",
    "pentagon", "supreme court", "fda", "cdc", "irs", "medicare", "medicaid",
    "california", "texas", "florida", "new york", "colorado", "michigan",
    "ohio", "georgia", "arizona", "pennsylvania", "illinois", "kentucky",
)


def _is_non_us(cand: Candidate) -> bool:
    """True if the story reads as non-US with no US anchor. Conservative:
    a story mentioning both (e.g. US tariffs on China) counts as US-relevant."""
    if not config.US_FOCUS_ENABLED:
        return False
    text = f" {cand.title or ''} {cand.summary or ''} ".lower()
    has_foreign = any(m in text for m in _NON_US_MARKERS)
    if not has_foreign:
        return False
    has_us = any(m in text for m in _US_MARKERS)
    return not has_us


def _is_question_title(cand: Candidate) -> bool:
    """Question headlines ('Are Apprenticeships The Answer?') are analysis or
    evergreen features, not news events. Excluded from briefings; still eligible
    as quick hits or By the Way items."""
    t = (cand.title or "").strip()
    if t.endswith("?"):
        return True
    first = t.split(" ", 1)[0].lower() if t else ""
    return first in ("why", "how", "what", "should", "can", "could", "is", "are",
                     "do", "does", "will")


# Investment-relevance scoring for the Money & Markets lane. The lane should
# prefer a concrete investment story (deal, earnings, stock move, IPO) over
# generic economic commentary — the 1440 "Apple Upgrade" model.
_INVESTMENT_WORDS = {
    "stock", "stocks", "shares", "shareholders", "investor", "investors",
    "investment", "ipo", "acquisition", "merger", "buyout", "stake",
    "earnings", "revenue", "profit", "valuation", "deal", "funding",
    "dividend", "buyback", "nasdaq", "dow", "billion", "trillion",
    "spinoff", "listing", "market value",
}


def _investment_score(cand: Candidate) -> int:
    text = f"{cand.title or ''} {cand.summary or ''}".lower()
    words = set(re.findall(r"[a-z&]+", text))
    score = sum(1 for w in _INVESTMENT_WORDS if (" " in w and w in text) or w in words)
    # Company-name signal: a capitalized proper noun in the title alongside a
    # dollar figure is a strong "investment story" tell.
    if re.search(r"\$[\d,.]+", cand.title or ""):
        score += 2
    return score


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


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _recency_key(cand: Candidate) -> datetime:
    """Sort key: parsed publish date, or epoch (sorts last) if unknown."""
    dt = _parse_pub_date(cand.published)
    return dt if dt else _EPOCH


def _recent_edition_urls(edition_date: str) -> set[str]:
    """URLs already published in editions within the last NO_REPEAT_DAYS.

    Scans editions/*.json dated strictly before edition_date (so a forced
    re-run of today regenerates freely). Collects every URL that appeared in
    a briefing source, quick hit source, or receipt. Per-file failures are
    silent — a corrupt or missing edition file never blocks the pipeline.
    """
    urls: set[str] = set()
    try:
        target = datetime.strptime(edition_date, "%Y-%m-%d").date()
    except ValueError:
        return urls
    cutoff = target - timedelta(days=config.NO_REPEAT_DAYS)
    for path in sorted(config.EDITIONS_DIR.glob("*.json")):
        try:
            d = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d >= target or d < cutoff:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for b in data.get("briefings") or []:
            for s in b.get("sources") or []:
                u = s.get("url")
                if u:
                    urls.add(u)
        for q in data.get("quick_hits") or []:
            u = (q.get("source") or {}).get("url")
            if u:
                urls.add(u)
        r = data.get("receipt")
        if r and r.get("source"):
            u = r["source"].get("url")
            if u:
                urls.add(u)
    return urls


def _classify_lane(cand: Candidate) -> int:
    """Lane assignment based on weighted keyword scoring.

    Lanes: 0=World/US, 1=Money, 2=Business/Policy, 3=Science/Tech/Health,
           4=Education, 5=Personal Excellence, 6=Real Estate, 7=Culture.

    Uses a score-per-lane approach instead of first-match, so a story about
    "a governor convicted of murdering a student" lands in World/US (murder,
    convicted, governor) rather than Education (student). Ties favor the
    lower-indexed (broader) lane.
    """
    text = f"{cand.title} {cand.summary}".lower()
    words = set(text.split())

    # Each lane gets a keyword set. Score = count of matches.
    lane_keywords = {
        0: {  # World / US — broad hard news, geopolitics, conflict, crime
            "war", "airstrike", "airstrikes", "invasion", "troops", "military",
            "missile", "missiles", "ceasefire", "conflict", "attack", "attacks",
            "killed", "murder", "convicted", "shooting", "bomb", "bombing",
            "terror", "terrorism", "refugee", "refugees", "sanctions",
            "diplomat", "diplomacy", "embassy", "treaty", "nato", "summit",
            "president", "prime minister", "government", "governor", "senator",
            "election", "vote", "votes", "voting", "ballot", "impeach",
            "protest", "protests", "riot", "crisis", "disaster", "earthquake",
            "hurricane", "tornado", "wildfire", "flood", "evacuation",
            "arrest", "arrested", "charged", "indicted", "convicted", "sentenced",
            "prison", "crime", "criminal", "homicide", "assault", "kidnapping",
            "accused", "alleged", "allegedly", "testified", "victims", "victim",
            "fraud", "manslaughter", "negligence", "inquest", "coroner",
            "funeral", "remains", "court", "guilty", "plea", "fined",
            "immigration", "deportation", "border", "asylum",
            "iran", "ukraine", "russia", "china", "nato", "pentagon",
            "tariff", "tariffs", "trade war", "sanctions",
        },
        1: {  # Money & Markets
            "market", "markets", "stock", "stocks", "dow", "nasdaq", "s&p",
            "fed", "federal reserve", "rate", "rates", "treasury", "yield",
            "inflation", "gdp", "economy", "economic", "recession",
            "bank", "banking", "mortgage", "investor", "investors",
            "earnings", "revenue", "profit", "losses", "rally", "selloff",
            "crypto", "bitcoin", "bonds", "commodity", "commodities",
            "wage", "wages", "unemployment", "jobs", "payroll",
            "remote work", "digital nomad", "relocation",
        },
        2: {  # Business / Policy
            "regulation", "antitrust", "ftc", "sec", "doj", "fcc",
            "congress", "legislation", "bill", "law", "ruling", "lawsuit",
            "merger", "acquisition", "ceo", "corporate", "startup",
            "monopoly", "privacy", "data protection", "compliance",
            "supreme court", "appeals court", "federal judge",
        },
        3: {  # Science / Tech / Health
            # NOTE: bare "trial" removed — it matched criminal trials and pulled
            # crime stories into this lane. "clinical trial" covers the medical use.
            "study", "research", "clinical trial", "clinical", "disease", "outbreak",
            "climate", "space", "nasa", "fda", "vaccine", "cancer", "drug",
            "ai", "artificial intelligence", "robot", "robotics",
            "gene", "genetic", "dna", "species", "fossil",
            "telescope", "satellite", "quantum", "algorithm",
            "virus", "bacteria", "pandemic", "epidemic", "cdc", "who",
            "surgery", "therapy", "diagnosis", "symptoms",
        },
        4: {  # Education
            "education", "curriculum", "tuition", "scholarship", "campus",
            "classroom", "principal", "professor", "degree", "enrollment",
            "school district", "school board", "higher education",
            "kindergarten", "elementary", "high school", "middle school",
            "charter school", "public school", "private school",
            "financial aid", "student loan", "student loans", "title ix",
            "early childhood", "preschool", "learning", "teacher", "teachers",
            "apprenticeship", "apprenticeships", "vocational",
        },
        5: {  # Personal Excellence — inspiring people, achievement, impact
            "inspiring", "hero", "heroes", "heroic", "rescue", "rescued",
            "milestone", "achievement", "award", "awarded", "honored",
            "honoured", "oldest", "youngest", "record-breaking",
            "volunteer", "volunteers", "donated", "donation", "donates",
            "overcame", "overcomes", "triumph", "graduates", "perseverance",
            "against the odds", "first person", "first woman", "first man",
            "scholarship winner", "saved", "saves",
        },
        6: {  # Real Estate
            "housing", "real estate", "home sales", "home prices",
            "homebuyer", "homebuyers", "eviction", "zoning",
            "construction", "apartment", "condo", "rental",
            "landlord", "tenant", "foreclosure", "affordable housing",
        },
        7: {  # Culture
            "museum", "festival", "arts", "film", "movie", "book", "novel",
            "music", "theater", "theatre", "exhibition", "literary",
            "comedy", "concert", "gallery", "sculpture", "painting",
            "streaming", "album", "documentary", "broadway",
        },
    }

    scores = {}
    for lane, kws in lane_keywords.items():
        score = 0
        for kw in kws:
            if ' ' in kw:
                # Multi-word keyword: check as substring
                if kw in text:
                    score += 1
            else:
                if kw in words:
                    score += 1
        scores[lane] = score

    # Pick the lane with the highest score. Ties favor lower index (broader lane).
    best_lane = 0
    best_score = scores.get(0, 0)
    for lane in sorted(scores.keys()):
        if scores[lane] > best_score:
            best_score = scores[lane]
            best_lane = lane

    return best_lane


def _pick_candidates(candidates: list[Candidate]) -> dict[int, list[Candidate]]:
    buckets: dict[int, list[Candidate]] = {i: [] for i in range(len(config.BRIEFING_LANES))}
    for c in candidates:
        lane = _classify_lane(c)
        if lane not in buckets:
            buckets[lane] = []
        buckets[lane].append(c)
    return buckets


def _title_signature(title: str) -> set[str]:
    """Extract distinctive words from a title for similarity comparison.

    Strips common stop words and returns the remaining lowercase words plus
    key numbers/amounts. Two stories with high overlap are likely duplicates.
    """
    stop = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and",
            "or", "but", "is", "are", "was", "were", "it", "its", "as",
            "by", "with", "from", "that", "this", "has", "have", "had",
            "be", "been", "not", "no", "new", "after", "how", "what",
            "who", "when", "where", "why", "says", "said", "more", "than",
            "first", "time", "since", "over", "into", "up", "out", "top"}
    words = set(re.findall(r'[a-z]+', title.lower()))
    # Normalize simple plurals so "apprenticeship" and "apprenticeships" match.
    words = {w[:-1] if (w.endswith('s') and not w.endswith('ss') and len(w) > 4)
             else w for w in words}
    # Include significant numbers (dollar amounts, percentages, large numbers)
    numbers = set(re.findall(r'\$?[\d,]+%?', title))
    return (words - stop) | numbers


def _is_duplicate(cand: Candidate, used_signatures: list[set[str]]) -> bool:
    """True if the candidate's title overlaps heavily with an already-used story."""
    sig = _title_signature(cand.title or '')
    if len(sig) < 2:
        return False
    for used_sig in used_signatures:
        if len(used_sig) < 2:
            continue
        overlap = sig & used_sig
        smaller = min(len(sig), len(used_sig))
        # If 40%+ of the smaller signature overlaps, it's likely the same story
        if smaller > 0 and len(overlap) / smaller >= 0.4:
            return True
        # Same-TOPIC rule: sharing one highly distinctive word (12+ chars, e.g.
        # "apprenticeship") means the edition already covers this topic. One
        # topic per edition — the second story is redundant even if the angle
        # differs.
        if any(isinstance(w, str) and len(w) >= 12 for w in overlap):
            return True
    return False


def _is_related_source(primary: Candidate, alt: Candidate) -> bool:
    """True if the alt candidate is about the same story as primary.

    Prevents unrelated RSS items (e.g. a quiz) from being added as a second
    source for a briefing about oil prices.
    """
    sig_primary = _title_signature(primary.title or '')
    sig_alt = _title_signature(alt.title or '')
    if not sig_primary or not sig_alt:
        return False
    overlap = sig_primary & sig_alt
    smaller = min(len(sig_primary), len(sig_alt))
    return smaller > 0 and len(overlap) / smaller >= 0.3


def _build_briefings(writer: ClaudeWriter, candidates: list[Candidate],
                     brave: Optional[BraveClient], log: EditionLogger,
                     published_urls: Optional[set[str]] = None
                     ) -> tuple[list[Briefing], list[set[str]]]:
    """Produce 4-6 briefings from discovered candidates.

    Core lanes (0-3: World/US, Money, Business/Policy, Science/Tech/Health)
    are attempted first and get Brave fallback. Optional lanes (4+: Education,
    Personal Excellence, Real Estate, Culture) fill remaining slots if available.

    Selection quality (per lane pool, before picking):
      - Freshness: candidates older than BRIEFING_MAX_AGE_HOURS are dropped.
      - History: URLs published within the last NO_REPEAT_DAYS are dropped.
      - Recency sort: remaining candidates are ordered newest-first, so the
        most recent qualifying story wins instead of whatever the feed
        happened to list first.

    Deduplication: stories with highly similar titles across different lanes are
    skipped after the first appearance. Source linking: second sources are only
    added if they are about the same story as the primary candidate.
    """
    published_urls = published_urls or set()
    buckets = _pick_candidates(candidates)
    lanes = config.BRIEFING_LANES
    briefings: list[Briefing] = []
    used_signatures: list[set[str]] = []
    non_us_used = 0

    # Core lanes first (0-3), then optional lanes (4+)
    core_count = min(4, len(lanes))
    lane_order = list(range(core_count)) + list(range(core_count, len(lanes)))

    for idx in lane_order:
        if len(briefings) >= config.N_BRIEFINGS_MAX:
            break
        lane_name = lanes[idx] if idx < len(lanes) else f"General {idx}"
        pool = buckets.get(idx, [])

        # Freshness + no-repeat + question-title filters, newest-first ordering
        pre_filter = len(pool)
        pool = [c for c in pool
                if _is_fresh(c, config.BRIEFING_MAX_AGE_HOURS)
                and c.url not in published_urls
                and not _is_question_title(c)]
        # Geography cap: once the non-US allowance is used, drop non-US stories.
        if non_us_used >= config.MAX_NON_US_BRIEFINGS:
            pool = [c for c in pool if not _is_non_us(c)]
        pool.sort(key=_recency_key, reverse=True)
        # Money & Markets lane prefers a concrete investment story (deal,
        # earnings, stock move) over generic economic commentary.
        if idx == 1:
            pool.sort(key=_investment_score, reverse=True)
        if pre_filter and len(pool) < pre_filter:
            log.info("briefing_pool_filtered", lane=idx,
                     before=pre_filter, after=len(pool))

        # Brave fallback only for core lanes (0-3)
        if not pool and brave and idx < core_count:
            query = _LANE_QUERIES.get(idx, "news today")
            try:
                pool = [c for c in brave.search(query, count=3)
                        if c.url not in published_urls]
                log.info("brave_fallback", lane=idx, query=query, results=len(pool))
            except (BraveDisabled, BraveCapExceeded) as e:
                log.warning("brave_unavailable", lane=idx, error=str(e)[:80])

        if not pool:
            # Core lanes (0-3) log a warning; optional lanes silently skip
            if idx < core_count:
                log.warning("lane_empty", lane=idx, name=lane_name)
            continue

        for cand in pool[:3]:
            # Skip if this story is essentially the same as one already picked
            if _is_duplicate(cand, used_signatures):
                log.info("briefing_dedup_skipped", lane=idx,
                         title=cand.title[:80])
                continue
            try:
                b = writer.write_briefing(cand, lane=lane_name)
            except (WriterDisabled, WriterBudgetExceeded):
                log.warning("writer_stopped", lane=idx)
                break
            if b:
                # Add a second source only if it's about the same story
                if idx in config.BRIEFING_TWO_SOURCE_INDICES and len(pool) > 1:
                    alt = [c for c in pool
                           if c.url != cand.url and _is_related_source(cand, c)]
                    if alt:
                        b.sources.append(Source(url=alt[0].url, title=alt[0].title,
                                                publisher=alt[0].publisher,
                                                published=alt[0].published))
                briefings.append(b)
                used_signatures.append(_title_signature(cand.title or ''))
                if _is_non_us(cand):
                    non_us_used += 1
                break

    return briefings, used_signatures


def _build_quick_hits(writer: ClaudeWriter, candidates: list[Candidate],
                      used_urls: set[str], brave: Optional[BraveClient],
                      target: int, log: EditionLogger,
                      used_signatures: Optional[list[set[str]]] = None
                      ) -> list[QuickHit]:
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

    used_signatures = list(used_signatures or [])
    hits: list[QuickHit] = []
    tried = 0
    non_us_used = 0
    for cand in ordered:
        if len(hits) >= target:
            break
        # Cross-section dedup: never repeat a topic already covered by a
        # briefing or an earlier quick hit.
        if _is_duplicate(cand, used_signatures):
            log.info("quick_hit_dedup_skipped", title=(cand.title or '')[:80])
            continue
        # Geography cap for quick hits.
        if _is_non_us(cand):
            if non_us_used >= config.MAX_NON_US_QUICK_HITS:
                continue
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
            used_signatures.append(_title_signature(cand.title or ''))
            if _is_non_us(cand):
                non_us_used += 1

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


# Whimsy signals for the "By the Way" light section — quirky, surprising, or
# delightful smaller stories (the 1440 "Etcetera" model).
_WHIMSY_WORDS = {
    "squirrel", "cat", "kitten", "dog", "puppy", "otter", "penguin", "moose",
    "bear", "raccoon", "parrot", "goat", "octopus", "alligator", "turtle",
    "oldest", "youngest", "record", "auction", "lottery", "jackpot",
    "message in a bottle", "time capsule", "reunited", "returned after",
    "unusual", "rare", "mystery", "mysterious", "accidentally", "surprise",
    "viral", "quirky", "bizarre", "world's largest", "world's smallest",
    "museum", "treasure", "shipwreck", "meteorite", "guinness",
}


def _whimsy_score(cand: Candidate) -> int:
    text = f"{cand.title or ''} {cand.summary or ''}".lower()
    words = set(re.findall(r"[a-z']+", text))
    return sum(1 for w in _WHIMSY_WORDS
               if (" " in w and w in text) or w in words)


def _build_by_the_way(writer: ClaudeWriter, candidates: list[Candidate],
                      used_urls: set[str],
                      used_signatures: list[set[str]],
                      log: EditionLogger) -> list[QuickHit]:
    """Produce 2-5 light one-liners for the 'By the Way' section.

    Prefers whimsical/odd stories (animals, records, auctions, curiosities);
    falls back to fresh Culture / Personal Excellence stories. Hard news
    (death, disaster, crime) is explicitly excluded — this section is the
    reader's dessert.
    """
    _HARD_NEWS_BLOCK = {"killed", "dead", "death", "dies", "murder", "shooting",
                        "war", "crash", "victims", "abuse", "assault", "fire",
                        "wildfire", "earthquake", "flood", "lawsuit", "charged",
                        "arrested", "cancer", "outbreak"}

    pool = []
    for c in candidates:
        if c.url in used_urls:
            continue
        if not _is_fresh(c, config.QUICK_HIT_MAX_AGE_HOURS):
            continue
        text_words = set(re.findall(r"[a-z]+",
                                     f"{c.title or ''} {c.summary or ''}".lower()))
        if text_words & _HARD_NEWS_BLOCK:
            continue
        if _is_duplicate(c, used_signatures):
            continue
        w = _whimsy_score(c)
        lane = _classify_lane(c)
        # Whimsy first; then light lanes (Culture=7, Personal Excellence=5).
        if w > 0:
            pool.append((c, 2 + w))
        elif lane in (5, 7):
            pool.append((c, 1))
    pool.sort(key=lambda x: x[1], reverse=True)

    hits: list[QuickHit] = []
    tried = 0
    for cand, _score in pool:
        if len(hits) >= config.N_BY_THE_WAY_MAX:
            break
        tried += 1
        if tried > 12:
            break
        try:
            qh = writer.write_by_the_way(cand)
        except (WriterDisabled, WriterBudgetExceeded):
            break
        if qh and qh.text:
            hits.append(qh)
            used_urls.add(cand.url)
            used_signatures.append(_title_signature(cand.title or ''))
    log.info("by_the_way_done", count=len(hits), pool=len(pool))
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
        if not _is_fresh(c, config.BRIEFING_MAX_AGE_HOURS):
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

    # 1b. Load publication history for the no-repeat window
    published_urls = _recent_edition_urls(edition_date)
    if published_urls:
        print(f"  No-repeat history: {len(published_urls)} URLs from the last "
              f"{config.NO_REPEAT_DAYS} days.")
        log.info("history_loaded", urls=len(published_urls),
                 days=config.NO_REPEAT_DAYS)

    # 2. Briefings (4-6)
    print(f"  [2/7] Writing briefings...")
    used_signatures: list[set[str]] = []
    try:
        briefings, used_signatures = _build_briefings(
            writer, candidates, brave, log, published_urls=published_urls)
    except Exception as e:
        print(f"  ERROR in briefings: {e}")
        briefings = []
    print(f"  Wrote {len(briefings)} briefings ({writer.calls_used} Claude calls used).")
    log.info("briefings_done", count=len(briefings),
             writer_calls=writer.calls_used)

    used_urls = {s.url for b in briefings for s in b.sources} | published_urls

    # 3. Quick hits — fill to reach 10-15 total articles
    print(f"  [3/7] Writing quick hits...")
    articles_so_far = len(briefings)
    qh_target = max(config.N_QUICK_HITS_MIN,
                    config.ARTICLE_TOTAL_MIN - articles_so_far)
    qh_target = min(qh_target, config.N_QUICK_HITS_MAX)
    try:
        quick_hits = _build_quick_hits(writer, candidates, used_urls, brave,
                                       qh_target, log,
                                       used_signatures=used_signatures)
    except Exception as e:
        print(f"  ERROR in quick hits: {e}")
        quick_hits = []
    print(f"  Wrote {len(quick_hits)} quick hits ({writer.calls_used} Claude calls used).")
    log.info("quick_hits_done", count=len(quick_hits),
             writer_calls=writer.calls_used)

    # 3b. By the Way — 2-5 light one-liners (quirky/delightful smaller stories)
    print(f"  [3b/8] Writing By the Way items...")
    try:
        btw_hits = _build_by_the_way(writer, candidates, used_urls,
                                     used_signatures, log)
    except Exception as e:
        print(f"  ERROR in By the Way: {e}")
        btw_hits = []
    print(f"  Wrote {len(btw_hits)} By the Way items.")
    # Stored alongside quick hits (lane='By the Way'); templates render them
    # as their own section. Keeps the schema unchanged.
    quick_hits = quick_hits + btw_hits

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

    # 7b. Cold open — 1440-style greeting teasing today's stories
    print(f"  [7b/8] Writing cold open...")
    date_readable = datetime.now(config.ET).strftime("%A, %B %d, %Y")
    cold_open_headlines = [b.headline for b in briefings if b.headline]
    cold_open_headlines += [q.text for q in quick_hits
                            if q.lane == config.BY_THE_WAY_LANE][:2]
    cold_open = ""
    try:
        cold_open = writer.write_cold_open(date_readable, cold_open_headlines)
    except Exception as e:
        print(f"  ERROR in cold open: {e}")
    if not cold_open:
        # Fail-safe fallback: plain greeting, never blocks the edition.
        weekday_date = datetime.now(config.ET).strftime("%A, %B %-d")
        cold_open = f"Good morning, it's {weekday_date}. Here's what you need to know today."
    print(f"  Cold open: {cold_open[:70]}...")

    # 8. Assemble
    ed = assemble_edition(
        edition_date, briefings, quick_hits, data_boxes, voice_blocks, closer,
        receipt=receipt,
        demo=False,
        extra_meta={
            "date_readable": date_readable,
            "cold_open": cold_open,
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
