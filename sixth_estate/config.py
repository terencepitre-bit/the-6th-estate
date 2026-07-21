"""Central configuration for THE 6th ESTATE daily edition system.

Every operational knob (model IDs, cost caps, feature flags, credentials) is read
from the environment so the code never carries secrets and deprecated model
versions can be swapped without edits. See .env.example for the full list.

SECURITY: no API keys, tokens, or personal emails are hardcoded here. Values that
look like addresses (sender, reply-to) are public brand identities, not secrets.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

# ── Paths ────────────────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
EDITIONS_DIR = REPO_ROOT / "editions"
STATE_DIR = REPO_ROOT / "state"
LOGS_DIR = REPO_ROOT / "logs"
SITE_DIR = REPO_ROOT / "site"
SITE_EDITIONS_DIR = SITE_DIR / "editions"
FIXTURES_DIR = REPO_ROOT / "fixtures"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ── Brand identity ─────────────────────────────────────────────────────────
BRAND = "THE 6th ESTATE"
TAGLINE = "The stories under the headlines."
PUBLISHER = "A Pitre Media Publication"
EDITOR = "Terence Pitre, PhD"
BYLINE_NEWSROOM = "The 6th Estate Newsroom"
CANONICAL_DOMAIN = _env("SIXTHE_CANONICAL_DOMAIN", "the6thestate.net")
CANONICAL_BASE_URL = f"https://{CANONICAL_DOMAIN}"

# ── Timezone ─────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/Detroit")


def today_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


# ── Canonical edition structure: flexible article counts ──────────────────────
# Briefings + Quick Hits should total 10-15. Data boxes, This Day, Receipt,
# and Closer are additional.
N_BRIEFINGS_MIN = 4
N_BRIEFINGS_MAX = 6
N_QUICK_HITS_MIN = 5
N_QUICK_HITS_MAX = 9
ARTICLE_TOTAL_MIN = 10   # briefings + quick hits combined floor
ARTICLE_TOTAL_MAX = 15   # briefings + quick hits combined ceiling
N_DATA_BOXES = 2         # Money Box + Sports Box
N_VOICE_BLOCKS = 1       # This Day only (The Number retired)
N_CLOSERS = 1
N_RECEIPTS_MAX = 1       # 0 or 1; only when a primary-source doc is available

# Word-count rules.
BRIEFING_WORDS = {"min": 60, "max": 75}
QUICK_HIT_MAX_WORDS = 25

# Recommended briefing lanes (guidance, not a hard gate).
BRIEFING_LANES = [
    "World / US lead",
    "Money & Markets (with a separate 'Why it matters' line)",
    "Business / Public Policy",
    "Science / Tech / Health or Real Estate (by impact)",
]

# Briefings that require two sources by default (lead + Money & Markets).
BRIEFING_TWO_SOURCE_INDICES = (0, 1)

# High-risk topics: two independent direct sources always required.
HIGH_RISK_TERMS = [
    "war", "invasion", "airstrike", "ceasefire",
    "election", "ballot", "voter", "recount",
    "allegation", "alleges", "accused", "indictment", "lawsuit", "charged",
    "abortion", "immigration", "deportation",
    "outbreak", "epidemic", "pandemic", "recall",
    "bankruptcy", "default", "collapse", "layoffs", "bailout",
]

# ── Publication floor ─────────────────────────────────────────────────────────
# Minimum validated items for auto-publish. Default: 10 articles + 2 boxes +
# 1 voice + 1 closer = 14. Manual preview may approve a reduced edition.
PUBLICATION_FLOOR = _env_int("SIXTHE_PUBLICATION_FLOOR",
                             ARTICLE_TOTAL_MIN + N_DATA_BOXES + N_VOICE_BLOCKS + N_CLOSERS)

# ── Automation posture ─────────────────────────────────────────────────────────
# Automation is DISABLED by default. Nothing publishes or emails unless the
# operator passes explicit flags AND sets the corresponding env vars.
AUTOMATION_ENABLED = _env_bool("SIXTHE_AUTOMATION_ENABLED", False)
DRY_RUN_DEFAULT = True

# ── Discovery: RSS-first, bounded fallback ────────────────────────────────────
# RSS feeds are free ($0). Configure via SIXTHE_RSS_FEEDS (comma-separated) or
# rely on the documented defaults below. Feeds must be authorized/permitted for
# reuse by the operator; these defaults are public agency/wire feeds.
def _rss_feeds() -> list[str]:
    raw = _env("SIXTHE_RSS_FEEDS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return list(DEFAULT_RSS_FEEDS)


DEFAULT_RSS_FEEDS = [
    "https://apnews.com/hub/ap-top-news?output=rss",   # verify permitted use
    "https://feeds.reuters.com/reuters/topNews",       # verify permitted use
    "https://www.bls.gov/feed/news_release.rss",       # public
    "https://www.federalreserve.gov/feeds/press_all.xml",  # public
    "https://www.weather.gov/rss",                     # public
]

# Brave Search fallback — only used to fill MISSING sections, capped per day.
BRAVE_SEARCH_ENABLED = _env_bool("SIXTHE_BRAVE_ENABLED", False)
BRAVE_API_KEY = _env("BRAVE_API_KEY")  # never logged
BRAVE_DAILY_QUERY_CAP = _env_int("SIXTHE_BRAVE_DAILY_CAP", 10)
BRAVE_API_BASE = _env("BRAVE_API_BASE", "https://api.search.brave.com/res/v1/web/search")

# Google Programmable Search — optional backup interface, DISABLED by default.
GOOGLE_PSE_ENABLED = _env_bool("SIXTHE_GOOGLE_PSE_ENABLED", False)
GOOGLE_PSE_KEY = _env("GOOGLE_PSE_KEY")
GOOGLE_PSE_CX = _env("GOOGLE_PSE_CX")
GOOGLE_PSE_BASE = _env("GOOGLE_PSE_BASE", "https://www.googleapis.com/customsearch/v1")

# SearXNG is intentionally NOT implemented; documented as a future option only.

# ── Data-box source endpoints (public data APIs) ──────────────────────────────
FRED_API_KEY = _env("FRED_API_KEY")  # never logged
FRED_API_BASE = _env("FRED_API_BASE", "https://api.stlouisfed.org/fred")
FRED_MORTGAGE_SERIES = "MORTGAGE30US"
BLS_API_KEY = _env("BLS_API_KEY")  # optional; public series work without it
BLS_API_BASE = _env("BLS_API_BASE", "https://api.bls.gov/publicAPI/v2")
BLS_CPI_SERIES = "CUUR0000SA0"  # CPI-U, all items, US city average
COINGECKO_API_BASE = _env("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3")
# Weather is DISABLED (national audience). Config kept for potential future use.
WEATHER_API_BASE = _env("WEATHER_API_BASE", "https://api.weather.gov")
WEATHER_FORECAST_URL = _env("SIXTHE_WEATHER_FORECAST_URL", "")
WIKIPEDIA_API_BASE = _env(
    "WIKIPEDIA_API_BASE", "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday"
)
# Sports: ESPN public scoreboard endpoints (no key required). Confirm permitted
# use before relying on these. Prefer official league feeds if available.
SPORTS_PROVIDER = _env("SIXTHE_SPORTS_PROVIDER", "espn")
SPORTS_API_BASE = _env("SPORTS_API_BASE",
                        "https://site.api.espn.com/apis/site/v2/sports")
SPORTS_LEAGUES = [s.strip() for s in
                  _env("SIXTHE_SPORTS_LEAGUES", "mlb,nba,nfl").split(",") if s.strip()]

# ── Model configuration (Gemini) ──────────────────────────────────────────────
# Model IDs are configurable so deprecated versions can be replaced without code
# ── Writer: Anthropic Claude API ──────────────────────────────────────────────
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")  # never logged
ANTHROPIC_API_BASE = _env("ANTHROPIC_API_BASE", "https://api.anthropic.com")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-4-6")

# Legacy Gemini config kept for backward compatibility
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_API_BASE = _env(
    "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_MODEL_BRIEFINGS = _env("GEMINI_MODEL_BRIEFINGS", "gemini-2.0-flash")
GEMINI_MODEL_QUICK_HITS = _env("GEMINI_MODEL_QUICK_HITS", "gemini-2.0-flash")
GEMINI_TEMPERATURE = float(_env("GEMINI_TEMPERATURE", "0.2") or 0.2)
# Hard ceiling on model calls per edition. Needs ~15 for full article set.
MODEL_CALL_LIMIT = _env_int("SIXTHE_MODEL_CALL_LIMIT", 20)

# ── Brevo email (sending gated) ────────────────────────────────────────────────
# Sending requires BOTH the --send flag AND SIXTHE_EMAIL_ENABLED=1 AND a proxied
# credential. No raw key is read or logged here.
EMAIL_ENABLED = _env_bool("SIXTHE_EMAIL_ENABLED", False)
BREVO_API_BASE = _env("BREVO_API_BASE", "https://api.brevo.com/v3")
BREVO_LIST_ID = _env_int("BREVO_LIST_ID", 11)  # "The 6th Estate - Daily Readers"
BREVO_LIST_NAME = "The 6th Estate - Daily Readers"
BREVO_SENDER_NAME = _env("BREVO_SENDER_NAME", "The 6th Estate")
BREVO_SENDER_EMAIL = _env("BREVO_SENDER_EMAIL", "news@the6thestate.net")
BREVO_REPLY_TO = _env("BREVO_REPLY_TO", "editor@the6thestate.net")


def word_count(text) -> int:
    """Whitespace word count. Non-strings count as 0."""
    if not isinstance(text, str):
        return 0
    return len(text.split())


# ── Direct-source URL validation ──────────────────────────────────────────────
# A published item must cite the SPECIFIC article/document/dataset — never a bare
# homepage, section index, search page, topic page, or tracking redirect. This is
# the single source of truth, imported by validators and the site generator so
# the definition of "direct" never drifts.
MIN_DIRECT_SOURCES = 1  # per-item floor; two-source items enforced separately

_DOC_EXTENSIONS = (".html", ".htm", ".pdf", ".aspx", ".php", ".jsp", ".xml", ".json")

# Hosts/paths that mark tracking redirects or search/aggregator pages -> rejected.
_TRACKING_HOSTS = (
    "news.google.com", "www.google.com/url", "l.facebook.com", "t.co",
    "lnkd.in", "flip.it", "trib.al",
)
_SEARCH_PATH_HINTS = ("/search", "/tag/", "/tags/", "/topic/", "/topics/", "/category/")


def _url_segment_is_specific(seg: str) -> bool:
    s = (seg or "").lower().strip()
    if not s:
        return False
    if s.endswith(_DOC_EXTENSIONS):
        return True
    tokens = [t for t in re.split(r"[-_]", s) if t]
    alpha_tokens = [t for t in tokens if t.isalpha() and len(t) >= 2]
    if ("-" in s or "_" in s) and len(alpha_tokens) >= 2:
        return True
    if re.search(r"\d", s):
        has_letter = bool(re.search(r"[a-z]", s))
        digit_count = len(re.sub(r"\D", "", s))
        if has_letter or digit_count >= 3 or "-" in s or "_" in s:
            return True
    return False


def is_generic_source_url(url) -> bool:
    """True if `url` is a bare host, section/index/landing/search/topic page, or a
    known tracking redirect rather than a direct article/document/dataset."""
    if not isinstance(url, str):
        return True
    u = url.strip()
    if not u:
        return True
    try:
        parsed = urlparse(u if "//" in u else "https://" + u)
    except Exception:
        return True
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return True
    full = (host + (parsed.path or "")).lower()
    if any(full.startswith(t) or host == t.split("/")[0] and t in full for t in _TRACKING_HOSTS):
        return True
    path = (parsed.path or "").lower()
    if any(hint in path for hint in _SEARCH_PATH_HINTS):
        return True
    segments = [s for s in (parsed.path or "").split("/") if s]
    if not segments:
        return True
    if any(_url_segment_is_specific(s) for s in segments):
        return False
    query = parsed.query or ""
    if query:
        for part in re.split(r"[&=]", query):
            if _url_segment_is_specific(part):
                return False
    return True


def direct_source_urls(*url_lists) -> list:
    """Merge citation lists (raw strings or {'url'/'href': ...} dicts), drop
    generic/landing/tracking URLs, and return distinct DIRECT URLs in order."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in url_lists:
        for entry in lst or []:
            if isinstance(entry, dict):
                raw = entry.get("url") or entry.get("href") or ""
            else:
                raw = entry
            if not isinstance(raw, str):
                continue
            u = raw.strip()
            if not u or is_generic_source_url(u):
                continue
            key = u.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
    return out


def ensure_dirs() -> None:
    for d in (EDITIONS_DIR, STATE_DIR, LOGS_DIR, SITE_EDITIONS_DIR, FIXTURES_DIR):
        d.mkdir(parents=True, exist_ok=True)
