"""Editorial validation gate for THE 6th ESTATE.

Validators are pure functions over an Edition (or its dict). They never touch the
network. Each returns findings; `validate_edition` aggregates them into a single
ValidationResult with an overall pass/fail decision.

Checks implemented:
  * section-count   — flexible: 4-6 briefings, 5-9 quick hits, 10-15 total articles
  * word-count      — briefings 60-75; quick hits <= 25
  * direct-source   — every cited URL is a specific article/document/dataset
  * free-access     — ALL sources must be free-access (strict, no paywalls ever)
  * high-risk       — two independent direct sources on war/elections/etc.
  * two-source lane — lead + Money & Markets briefings require two sources
  * factual-field   — data-box metrics and voice blocks carry source + as-of
  * freshness       — sources dated within a configurable window (when dated)
  * receipt         — if present, must have free-access direct source
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from .. import config
from ..schema import Edition


@dataclass
class ItemFinding:
    item: str            # human-readable item id, e.g. "briefing[0]"
    level: str           # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    ok: bool
    findings: list[ItemFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[ItemFinding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[ItemFinding]:
        return [f for f in self.findings if f.level == "warning"]

    def summary(self) -> str:
        return (
            f"{'PASS' if self.ok else 'FAIL'} — "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


def _host(url: str) -> str:
    try:
        return (urlparse(url if "//" in url else "https://" + url).netloc or "").lower()
    except Exception:
        return ""


def _direct(urls) -> list[str]:
    return config.direct_source_urls(urls)


def _distinct_hosts(urls) -> int:
    return len({_host(u) for u in urls if _host(u)})


def _is_high_risk(text: str) -> bool:
    low = (text or "").lower()
    # Word-boundary match so 'war' does not fire inside 'warned' / 'toward'.
    return any(re.search(rf"\b{re.escape(term)}\b", low) for term in config.HIGH_RISK_TERMS)


def _dataset_source_ok(url) -> bool:
    """Looser gate for Data Box / Voice Block sources.

    Data boxes and voice blocks cite CANONICAL reference/dataset pages — a FRED
    series page, a CoinGecko coin page, a BLS CPI page, a Wikipedia article, an
    NWS gridpoint. These are legitimately 'the source' even when the final slug
    is a single word, so a bare homepage is still rejected but a path-bearing
    canonical page is accepted. News-article items (briefings/quick hits) keep
    the strict is_generic_source_url gate."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url if "//" in url else "https://" + url)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if not host:
        return False
    if any(t.split("/")[0] in host for t in config._TRACKING_HOSTS):
        return False
    path = (parsed.path or "").lower()
    if any(hint in path for hint in config._SEARCH_PATH_HINTS):
        return False
    segments = [s for s in (parsed.path or "").split("/") if s]
    return len(segments) >= 1


def _parse_date(s: str):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# ── Individual checks ─────────────────────────────────────────────────────────
def check_section_counts(ed: Edition) -> list[ItemFinding]:
    out = []
    nb = len(ed.briefings)
    nq = len(ed.quick_hits)
    total_articles = nb + nq

    if nb < config.N_BRIEFINGS_MIN:
        out.append(ItemFinding("briefings", "error",
                               f"need at least {config.N_BRIEFINGS_MIN}, found {nb}"))
    if nb > config.N_BRIEFINGS_MAX:
        out.append(ItemFinding("briefings", "warning",
                               f"found {nb}, max is {config.N_BRIEFINGS_MAX}"))
    if nq < config.N_QUICK_HITS_MIN:
        out.append(ItemFinding("quick_hits", "error",
                               f"need at least {config.N_QUICK_HITS_MIN}, found {nq}"))
    if total_articles < config.ARTICLE_TOTAL_MIN:
        out.append(ItemFinding("articles", "error",
                               f"briefings+quick_hits={total_articles}; "
                               f"need at least {config.ARTICLE_TOTAL_MIN}"))
    if total_articles > config.ARTICLE_TOTAL_MAX:
        out.append(ItemFinding("articles", "warning",
                               f"briefings+quick_hits={total_articles}; "
                               f"max is {config.ARTICLE_TOTAL_MAX}"))
    if len(ed.data_boxes) < config.N_DATA_BOXES:
        out.append(ItemFinding("data_boxes", "warning",
                               f"expected {config.N_DATA_BOXES}, found {len(ed.data_boxes)}"))
    if (ed.closer is None) or not (ed.closer.text or "").strip():
        out.append(ItemFinding("closer", "error", "exactly one closer is required"))
    return out


def check_briefings(ed: Edition, freshness_days: int) -> list[ItemFinding]:
    out = []
    for i, b in enumerate(ed.briefings):
        tag = f"briefing[{i}]"
        wc = config.word_count(b.body)
        lo, hi = config.BRIEFING_WORDS["min"], config.BRIEFING_WORDS["max"]
        if not (lo <= wc <= hi):
            out.append(ItemFinding(tag, "error",
                                   f"body is {wc} words; must be {lo}-{hi}"))
        direct = _direct([s.url for s in b.sources])
        if not direct:
            out.append(ItemFinding(tag, "error", "no direct source URL"))
        # Strict free-access: no paywalled sources, ever.
        for si, s in enumerate(b.sources):
            if not s.free_access:
                out.append(ItemFinding(tag, "error",
                                       f"source[{si}] is paywalled — free-access only"))
        # Two-source requirement: designated lanes OR high-risk content.
        high_risk = b.high_risk or _is_high_risk(b.headline + " " + b.body)
        needs_two = high_risk or (i in config.BRIEFING_TWO_SOURCE_INDICES)
        if needs_two and _distinct_hosts(direct) < 2:
            reason = "high-risk topic" if high_risk else "lead/Money lane"
            out.append(ItemFinding(tag, "error",
                                   f"{reason} requires two independent direct sources"))
        # Money & Markets lane must carry a 'why it matters' line.
        if i == 1 and not (b.why_it_matters or "").strip():
            out.append(ItemFinding(tag, "error",
                                   "Money & Markets briefing needs a 'why it matters' line"))
        out.extend(_freshness_findings(tag, b.sources, freshness_days))
    return out


def check_quick_hits(ed: Edition, freshness_days: int) -> list[ItemFinding]:
    out = []
    for i, q in enumerate(ed.quick_hits):
        tag = f"quick_hit[{i}]"
        wc = config.word_count(q.text)
        if wc > config.QUICK_HIT_MAX_WORDS:
            out.append(ItemFinding(tag, "error",
                                   f"{wc} words; max {config.QUICK_HIT_MAX_WORDS}"))
        if not q.source or config.is_generic_source_url(q.source.url):
            out.append(ItemFinding(tag, "error", "needs one exact direct source"))
        elif not q.source.free_access:
            out.append(ItemFinding(tag, "error",
                                   "source is not marked free-access (no paywalled links)"))
        if q.source:
            out.extend(_freshness_findings(tag, [q.source], freshness_days))
    return out


def check_data_boxes(ed: Edition) -> list[ItemFinding]:
    out = []
    for i, box in enumerate(ed.data_boxes):
        tag = f"data_box[{i}]"
        if not box.metrics:
            out.append(ItemFinding(tag, "error", "data box has no metrics"))
        for j, m in enumerate(box.metrics):
            mtag = f"{tag}.metric[{j}]"
            if not (m.value or "").strip():
                out.append(ItemFinding(mtag, "error", "metric has no value"))
            if not m.source or not _dataset_source_ok(m.source.url):
                out.append(ItemFinding(mtag, "error", "metric needs a direct source"))
            if not (m.as_of or "").strip():
                out.append(ItemFinding(mtag, "error", "metric needs an as-of timestamp"))
    return out


def check_voice_blocks(ed: Edition) -> list[ItemFinding]:
    out = []
    for i, v in enumerate(ed.voice_blocks):
        tag = f"voice_block[{i}]"
        if not (v.text or "").strip():
            out.append(ItemFinding(tag, "error", "voice block has no text"))
        if not v.source or not _dataset_source_ok(v.source.url):
            out.append(ItemFinding(tag, "error", "voice block needs a direct source"))
        if not (v.as_of or "").strip():
            out.append(ItemFinding(tag, "warning", "voice block missing as-of timestamp"))
    return out


def check_closer(ed: Edition) -> list[ItemFinding]:
    out = []
    if not ed.closer:
        return out
    if ed.closer.factual and (
        not ed.closer.source or config.is_generic_source_url(ed.closer.source.url)
    ):
        out.append(ItemFinding("closer", "error",
                               "factual/quoted closer must cite a direct source"))
    return out


def check_receipt(ed: Edition) -> list[ItemFinding]:
    out = []
    if not ed.receipt:
        return out  # receipt is optional (0 or 1)
    tag = "receipt"
    if not (ed.receipt.title or "").strip():
        out.append(ItemFinding(tag, "error", "receipt needs a title"))
    if not (ed.receipt.description or "").strip():
        out.append(ItemFinding(tag, "error", "receipt needs a description"))
    if not ed.receipt.source or config.is_generic_source_url(ed.receipt.source.url):
        out.append(ItemFinding(tag, "error", "receipt needs a direct source URL"))
    elif not ed.receipt.source.free_access:
        out.append(ItemFinding(tag, "error",
                               "receipt source must be free-access (no paywalls)"))
    return out


def _freshness_findings(tag, sources, freshness_days) -> list[ItemFinding]:
    if freshness_days <= 0:
        return []
    out = []
    cutoff = date.today() - timedelta(days=freshness_days)
    for s in sources:
        d = _parse_date(getattr(s, "published", "") or "")
        if d and d < cutoff:
            out.append(ItemFinding(tag, "warning",
                                   f"source dated {d.isoformat()} older than "
                                   f"{freshness_days}d window"))
    return out


def validate_edition(edition, freshness_days: int = 3) -> ValidationResult:
    """Run all checks. `freshness_days<=0` disables freshness (useful for demo
    fixtures whose sources are intentionally undated)."""
    ed = edition if isinstance(edition, Edition) else Edition.from_dict(edition)
    findings: list[ItemFinding] = []
    findings += check_section_counts(ed)
    findings += check_briefings(ed, freshness_days)
    findings += check_quick_hits(ed, freshness_days)
    findings += check_data_boxes(ed)
    findings += check_voice_blocks(ed)
    findings += check_closer(ed)
    findings += check_receipt(ed)
    ok = not any(f.level == "error" for f in findings)
    return ValidationResult(ok=ok, findings=findings)
