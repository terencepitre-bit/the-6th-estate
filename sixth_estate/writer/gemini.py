"""Gemini writer interface — source-bound, batched, hard-bounded, safe-failing.

Cost guardrails (all configurable via env, see config.py):
  * Two models: a Flash-class model for Briefings, a Flash-Lite-class model for
    Quick Hits. Model IDs come from env so deprecated versions swap without edits.
  * MODEL_CALL_LIMIT caps total calls per edition (one batched pass + at most one
    fallback). No repair loops.
  * Low temperature by default; deterministic-leaning.
  * Prompts are SOURCE-BOUND: the model may only summarize the candidate text and
    must not introduce facts or URLs. If generation fails or the budget is spent,
    the writer fails safe (raises / returns None) rather than fabricating.

The API key is read from config (env) and never logged. `transport` is injectable
so tests exercise prompt-building and budgeting with zero network calls.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from .. import config
from ..discovery.candidate import Candidate
from ..http_util import post_json
from ..schema import Briefing, QuickHit, Source


class WriterDisabled(RuntimeError):
    pass


class WriterBudgetExceeded(RuntimeError):
    pass


_BRIEFING_SYSTEM = (
    "You are a neutral wire editor for THE 6th ESTATE. Summarize ONLY the supplied "
    "source text. Do not add facts, names, quotes, or URLs not present in the "
    "sources. Write 60-75 words, factual and non-editorial. Build in practical "
    "impact: explain WHY this matters to readers and what it could mean for them. "
    "Prefer 'could' over 'should' when consequences are uncertain. Return strict JSON."
)
_QUICK_HIT_SYSTEM = (
    "You are a neutral wire editor for THE 6th ESTATE. Compress the supplied source "
    "into a single factual sentence of 25 words or fewer. No opinion, no added "
    "facts, no URLs. Return strict JSON."
)


class GeminiWriter:
    def __init__(self, transport: Optional[Callable] = None, logger=None,
                 call_limit: Optional[int] = None):
        self.api_key = config.GEMINI_API_KEY
        self.enabled = bool(self.api_key) or transport is not None
        self._transport = transport
        self.logger = logger
        self.call_limit = call_limit if call_limit is not None else config.MODEL_CALL_LIMIT
        self._calls = 0

    @property
    def calls_used(self) -> int:
        return self._calls

    # ── prompt builders (pure) ────────────────────────────────────────────────
    def build_briefing_prompt(self, cand: Candidate) -> str:
        return (
            f"SOURCE TITLE: {cand.title}\nSOURCE SUMMARY: {cand.summary}\n"
            f"PUBLISHER: {cand.publisher}\n"
            "Write the briefing body now as JSON: {\"headline\":..., \"body\":..., "
            "\"why_it_matters\":...}."
        )

    def build_quick_hit_prompt(self, cand: Candidate) -> str:
        return (
            f"SOURCE TITLE: {cand.title}\nSOURCE SUMMARY: {cand.summary}\n"
            "Write the quick hit now as JSON: {\"text\":...}."
        )

    # ── generation (bounded) ──────────────────────────────────────────────────
    def _call(self, model: str, system: str, prompt: str) -> dict:
        if not self.enabled:
            raise WriterDisabled("Gemini writer disabled (no GEMINI_API_KEY / transport)")
        if self._calls >= self.call_limit:
            raise WriterBudgetExceeded(f"model call limit {self.call_limit} reached")
        self._calls += 1
        if self.logger:
            self.logger.info("model_call", model=model, n=self._calls, cap=self.call_limit)
        if self._transport is not None:
            return self._transport(model, system, prompt)
        url = f"{config.GEMINI_API_BASE}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": config.GEMINI_TEMPERATURE,
                                 "responseMimeType": "application/json"},
        }
        return post_json(url, payload)

    @staticmethod
    def _extract_json(resp: dict) -> dict:
        # Real Gemini shape: candidates[0].content.parts[0].text (JSON string).
        try:
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            # Test transports may return the parsed dict directly.
            if isinstance(resp, dict) and ("body" in resp or "text" in resp):
                return resp
            raise

    def write_briefing(self, cand: Candidate, lane: str = "") -> Optional[Briefing]:
        """Return a source-bound Briefing, or None on failure (fail safe)."""
        try:
            resp = self._call(config.GEMINI_MODEL_BRIEFINGS, _BRIEFING_SYSTEM,
                              self.build_briefing_prompt(cand))
            data = self._extract_json(resp)
        except (WriterDisabled, WriterBudgetExceeded):
            raise
        except Exception as e:
            if self.logger:
                self.logger.warning("briefing_gen_failed", url=cand.url, error=str(e)[:120])
            return None
        return Briefing(
            headline=data.get("headline") or cand.title,
            body=data.get("body", ""),
            why_it_matters=data.get("why_it_matters", ""),
            lane=lane,
            sources=[Source(url=cand.url, title=cand.title, publisher=cand.publisher,
                            published=cand.published)],
        )

    def write_quick_hit(self, cand: Candidate, lane: str = "") -> Optional[QuickHit]:
        try:
            resp = self._call(config.GEMINI_MODEL_QUICK_HITS, _QUICK_HIT_SYSTEM,
                              self.build_quick_hit_prompt(cand))
            data = self._extract_json(resp)
        except (WriterDisabled, WriterBudgetExceeded):
            raise
        except Exception as e:
            if self.logger:
                self.logger.warning("quick_hit_gen_failed", url=cand.url, error=str(e)[:120])
            return None
        return QuickHit(
            text=data.get("text", ""), lane=lane,
            source=Source(url=cand.url, title=cand.title, publisher=cand.publisher,
                          published=cand.published, free_access=True),
        )
