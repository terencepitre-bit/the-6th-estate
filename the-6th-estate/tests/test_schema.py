from helpers import valid_edition

from sixth_estate.schema import Edition


def test_edition_roundtrip():
    ed = valid_edition()
    d = ed.to_dict()
    ed2 = Edition.from_dict(d)
    assert ed2.date == ed.date
    assert len(ed2.briefings) == 4
    assert len(ed2.quick_hits) == 5
    assert len(ed2.data_boxes) == 2
    assert len(ed2.voice_blocks) == 2
    assert ed2.closer is not None
    assert ed2.to_dict() == d  # stable serialization


def test_save_and_load(tmp_path):
    ed = valid_edition()
    p = ed.save(tmp_path / "e.json")
    loaded = Edition.load(p)
    assert loaded.briefings[1].why_it_matters == "It affects household budgets."


def test_all_sources_collects_every_item():
    ed = valid_edition()
    srcs = ed.all_sources()
    # 2+2+1+1 briefings + 5 quick hits + data-box metrics + 2 voice + 1 closer
    assert len(srcs) >= 14
    assert all(s.url for s in srcs)


def test_demo_flag_preserved():
    ed = valid_edition()
    assert ed.demo is True
    assert Edition.from_dict(ed.to_dict()).demo is True
