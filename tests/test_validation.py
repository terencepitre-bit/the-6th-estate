from helpers import valid_edition

from sixth_estate import config
from sixth_estate.schema import Source
from sixth_estate.validation import validate_edition


def test_valid_edition_passes():
    r = validate_edition(valid_edition(), freshness_days=0)
    assert r.ok, r.summary() + " :: " + "; ".join(f"{f.item}:{f.message}" for f in r.errors)


def test_wrong_section_counts_fail():
    ed = valid_edition()
    ed.briefings = ed.briefings[:3]        # only 3 briefings
    r = validate_edition(ed, freshness_days=0)
    assert not r.ok
    assert any("briefings" in f.item for f in r.errors)


def test_briefing_wordcount_enforced():
    ed = valid_edition()
    ed.briefings[0].body = "too short"
    r = validate_edition(ed, freshness_days=0)
    assert any(f.item == "briefing[0]" and "words" in f.message for f in r.errors)


def test_quick_hit_wordcount_enforced():
    ed = valid_edition()
    ed.quick_hits[0].text = " ".join(["w"] * 40)  # over 25
    r = validate_edition(ed, freshness_days=0)
    assert any(f.item == "quick_hit[0]" for f in r.errors)


def test_quick_hit_paywalled_source_rejected():
    ed = valid_edition()
    ed.quick_hits[0].source.free_access = False
    r = validate_edition(ed, freshness_days=0)
    assert any("free-access" in f.message for f in r.errors)


def test_generic_url_rejected_for_briefing():
    ed = valid_edition()
    ed.briefings[2].sources = [Source(url="https://example.com/")]  # bare host
    r = validate_edition(ed, freshness_days=0)
    assert any(f.item == "briefing[2]" for f in r.errors)


def test_money_lane_requires_why_it_matters():
    ed = valid_edition()
    ed.briefings[1].why_it_matters = ""
    r = validate_edition(ed, freshness_days=0)
    assert any("why it matters" in f.message for f in r.errors)


def test_lead_and_money_require_two_sources():
    ed = valid_edition()
    ed.briefings[0].sources = ed.briefings[0].sources[:1]  # drop to one host
    r = validate_edition(ed, freshness_days=0)
    assert any("two independent" in f.message for f in r.errors)


def test_high_risk_requires_two_sources():
    ed = valid_edition()
    # Ordinary lane (index 2) normally needs one source; make it high-risk.
    ed.briefings[2].headline = "Election recount ordered after lawsuit"
    r = validate_edition(ed, freshness_days=0)
    assert any(f.item == "briefing[2]" and "two independent" in f.message for f in r.errors)


def test_warned_does_not_trip_high_risk():
    # 'war' must not match inside 'warned' — single-source ordinary briefing is fine.
    ed = valid_edition()
    ed.briefings[2].body = ("Officials warned about compliance costs toward the "
                            + " ".join(["word"] * 55))
    r = validate_edition(ed, freshness_days=0)
    assert not any(f.item == "briefing[2]" and "two independent" in f.message for f in r.errors)


def test_data_box_metric_requires_as_of():
    ed = valid_edition()
    ed.data_boxes[0].metrics[0].as_of = ""
    r = validate_edition(ed, freshness_days=0)
    assert any("as-of" in f.message for f in r.errors)


def test_factual_closer_requires_source():
    ed = valid_edition()
    ed.closer.source = None
    r = validate_edition(ed, freshness_days=0)
    assert any(f.item == "closer" for f in r.errors)


def test_structure_constants():
    assert config.ARTICLE_TOTAL_MIN == 10
    assert config.ARTICLE_TOTAL_MAX == 15
    assert config.N_BRIEFINGS_MIN == 4
    assert config.N_QUICK_HITS_MIN == 5
