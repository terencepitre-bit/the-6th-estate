"""Tests for quick hit interest scoring, date parsing, and recency filtering."""
from datetime import datetime, timedelta, timezone

from sixth_estate.discovery.candidate import Candidate
from sixth_estate.pipeline import _score_interest, _parse_pub_date, _is_fresh


# ── Interest scoring ─────────────────────────────────────────────────────────

def _cand(title, summary="A detailed summary of the story for context."):
    return Candidate(title=title, url="https://example.com/story-123",
                     summary=summary, publisher="Test")


def test_high_interest_action_verb():
    c = _cand("White House Bans TikTok for Federal Employees")
    assert _score_interest(c) >= 3


def test_high_interest_number():
    c = _cand("$4.2 Billion Infrastructure Bill Passes Senate")
    assert _score_interest(c) >= 4


def test_high_interest_percentage():
    c = _cand("Mortgage Rates Drop 12% in Biggest Weekly Decline")
    assert _score_interest(c) >= 4


def test_low_interest_bureaucratic():
    c = _cand("Technical Correction to Docket Rulemaking Addendum",
              summary="Pursuant to the memorandum, the solicitation is codified.")
    assert _score_interest(c) <= 2


def test_low_interest_no_summary():
    c = _cand("Lizard Status Changed", summary="")
    assert _score_interest(c) <= 2


def test_mid_interest_proper_noun_only():
    c = _cand("Something About Microsoft Today")
    assert _score_interest(c) >= 2


def test_score_clamped_to_range():
    # Even a maximally boring story shouldn't go below 1
    c = _cand("x", summary="")
    score = _score_interest(c)
    assert 1 <= score <= 5

    # Even a maximally interesting story shouldn't exceed 5
    c2 = _cand("$500 Billion Emergency: White House Bans Historic 90% Tax Cuts",
               summary="Workers and families face unprecedented crisis.")
    score2 = _score_interest(c2)
    assert 1 <= score2 <= 5


# ── Date parsing ─────────────────────────────────────────────────────────────

def test_parse_rfc2822():
    dt = _parse_pub_date("Wed, 23 Jul 2026 12:00:00 GMT")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 7 and dt.day == 23


def test_parse_iso8601():
    dt = _parse_pub_date("2026-07-23T08:00:00Z")
    assert dt is not None
    assert dt.year == 2026


def test_parse_iso8601_with_offset():
    dt = _parse_pub_date("2026-07-23T08:00:00+00:00")
    assert dt is not None


def test_parse_bare_date():
    dt = _parse_pub_date("2026-07-23")
    assert dt is not None
    assert dt.year == 2026


def test_parse_empty_returns_none():
    assert _parse_pub_date("") is None
    assert _parse_pub_date("   ") is None


def test_parse_garbage_returns_none():
    assert _parse_pub_date("not a date at all") is None


# ── Recency filtering ───────────────────────────────────────────────────────

def test_fresh_candidate_passes():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c = _cand("Fresh Story")
    c.published = now_iso
    assert _is_fresh(c, max_age_hours=36) is True


def test_stale_candidate_filtered():
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c = _cand("Old Story")
    c.published = old
    assert _is_fresh(c, max_age_hours=36) is False


def test_unknown_date_kept():
    c = _cand("Mystery Story")
    c.published = ""
    assert _is_fresh(c, max_age_hours=36) is True


def test_unparseable_date_kept():
    c = _cand("Weird Date Story")
    c.published = "sometime last week maybe"
    assert _is_fresh(c, max_age_hours=36) is True
