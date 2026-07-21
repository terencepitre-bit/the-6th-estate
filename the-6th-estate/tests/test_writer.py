from sixth_estate.discovery.candidate import Candidate
from sixth_estate.writer import GeminiWriter, WriterBudgetExceeded, WriterDisabled


def _cand():
    return Candidate(title="Deep report on housing", url="https://ex.gov/report-12345",
                     summary="Housing starts rose.", publisher="Census")


def test_writer_disabled_without_key_or_transport():
    w = GeminiWriter(transport=None)
    w.enabled = False
    try:
        w.write_briefing(_cand())
        assert False
    except WriterDisabled:
        pass


def test_writer_produces_source_bound_briefing():
    def transport(model, system, prompt):
        return {"headline": "Housing starts climb", "body": "Body text.",
                "why_it_matters": "Matters."}
    w = GeminiWriter(transport=transport)
    b = w.write_briefing(_cand(), lane="Money & Markets")
    assert b.headline == "Housing starts climb"
    # Source URL is bound to the candidate, never invented by the model.
    assert b.sources[0].url == "https://ex.gov/report-12345"
    assert w.calls_used == 1


def test_writer_call_budget_enforced():
    def transport(model, system, prompt):
        return {"text": "x"}
    w = GeminiWriter(transport=transport, call_limit=1)
    w.write_quick_hit(_cand())
    try:
        w.write_quick_hit(_cand())
        assert False
    except WriterBudgetExceeded:
        pass


def test_writer_fails_safe_on_bad_response():
    def transport(model, system, prompt):
        raise ValueError("garbage")
    w = GeminiWriter(transport=transport)
    assert w.write_briefing(_cand()) is None  # returns None, does not fabricate
