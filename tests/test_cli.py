import sixth_estate.config as config
from helpers import valid_edition
from sixth_estate import cli
from sixth_estate.state import APPROVED, EDIT_HOLD, SKIPPED, EditionState


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDITIONS_DIR", tmp_path / "editions")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "SITE_DIR", tmp_path / "site")
    monkeypatch.setattr(config, "SITE_EDITIONS_DIR", tmp_path / "site" / "editions")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    for d in (config.EDITIONS_DIR, config.STATE_DIR, config.SITE_EDITIONS_DIR, config.LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _write_valid(date="2026-07-20"):
    ed = valid_edition(date)
    ed.save(config.EDITIONS_DIR / f"{date}.json")
    return ed


def _args(**kw):
    class A:
        pass
    a = A()
    a.__dict__.update({"date": "2026-07-20", "freshness": 0, "force": False,
                       "render": False, "floor": None, "note": "", "send": False})
    a.__dict__.update(kw)
    return a


def test_preview_reports_pass(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    _write_valid()
    rc = cli.cmd_preview(_args())
    assert rc == 0
    assert "PASS" in capsys.readouterr().out


def test_approve_then_publish(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _write_valid()
    assert cli.cmd_approve(_args()) == 0
    assert EditionState.load_or_new("2026-07-20").status == APPROVED
    assert cli.cmd_publish(_args()) == 0
    st = EditionState.load_or_new("2026-07-20")
    assert st.published is True
    assert (config.SITE_DIR / "editions" / "2026-07-20.html").exists()


def test_skip_blocks_publish(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _write_valid()
    cli.cmd_skip(_args())
    assert EditionState.load_or_new("2026-07-20").status == SKIPPED
    assert cli.cmd_publish(_args()) == 1  # refused


def test_edit_hold_blocks_publish(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _write_valid()
    cli.cmd_edit(_args(note="fix headline"))
    st = EditionState.load_or_new("2026-07-20")
    assert st.status == EDIT_HOLD and "fix headline" in st.notes
    assert cli.cmd_publish(_args()) == 1


def test_publish_requires_approval(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _write_valid()
    # Not approved and not forced -> refuse.
    assert cli.cmd_publish(_args()) == 1


def test_approve_refuses_invalid_edition(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ed = valid_edition()
    ed.briefings = ed.briefings[:2]  # invalid: wrong count
    ed.save(config.EDITIONS_DIR / "2026-07-20.json")
    assert cli.cmd_approve(_args()) == 2
