import sixth_estate.config as config
from helpers import valid_edition
from sixth_estate.email import EmailSendDisabled, build_email_html, send_edition
from sixth_estate.state import EditionState


def test_state_idempotent_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    st = EditionState.load_or_new("2026-07-20")
    assert st.mark_published("t1") is True
    assert st.mark_published("t2") is False   # already published -> no-op
    assert st.published_at == "t1"


def test_email_html_contains_all_sections():
    html = build_email_html(valid_edition())
    for label in ("Briefings", "Quick Hits", "Data Boxes", "Voice Blocks", "The Closer"):
        assert label in html
    assert "DEMO EDITION" in html  # demo banner present


def test_send_dry_run_does_not_send():
    ed = valid_edition()
    st = EditionState(date=ed.date)
    res = send_edition(ed, st, send=False)
    assert res["sent"] is False
    assert not st.emailed


def test_send_refused_when_flag_set_but_email_disabled(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    ed = valid_edition()
    st = EditionState(date=ed.date)
    try:
        send_edition(ed, st, send=True, transport=lambda p: {"id": 1})
        assert False
    except EmailSendDisabled:
        pass


def test_send_gated_success_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    ed = valid_edition()
    st = EditionState.load_or_new(ed.date)
    calls = {"n": 0}

    def transport(payload):
        calls["n"] += 1
        assert payload["recipients"]["listIds"] == [config.BREVO_LIST_ID]
        assert payload["sender"]["email"] == config.BREVO_SENDER_EMAIL
        return {"id": 555}

    res = send_edition(ed, st, send=True, transport=transport)
    assert res["sent"] and res["campaign_id"] == 555
    # Second attempt is an idempotent no-op (no second campaign created).
    res2 = send_edition(ed, st, send=True, transport=transport)
    assert res2["sent"] is False
    assert calls["n"] == 1
