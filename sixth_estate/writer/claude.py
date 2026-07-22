"""Claude (Anthropic) writer interface — source-bound, batched, safe-failing.

Uses the Anthropic Messages API (/v1/messages) for all writing. Same editorial
guardrails as the original Gemini writer: source-bound, bounded budget, no
fabrication, fail-safe.

The API key is read from config (env) and never logged.
"""
from __future__ import annotations

import json
import time
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
    "Prefer 'could' over 'should' when consequences are uncertain. "
    "The 'why_it_matters' field should be a standalone sentence explaining real-world "
    "impact on people, not a restatement of the headline. "
    "Do NOT include any parenthetical notes, meta-instructions, or guidance text "
    "in any field. Every field should read as clean, publishable prose. "
    "Return ONLY a JSON object with keys: headline, body, why_it_matters. "
    "No markdown, no code fences, no preamble."
)
_QUICK_HIT_SYSTEM = (
    "You are a neutral wire editor for THE 6th ESTATE. Compress the supplied source "
    "into a single factual sentence of 25 words or fewer. The sentence should be a "
    "complete, impactful statement — not a fragment or bare headline. Include a "
    "specific number, name, or concrete detail that makes it interesting. "
    "No opinion, no added facts, no URLs. "
    "Return ONLY a JSON object with key: text. "
    "No markdown, no code fences, no preamble."
)


class ClaudeWriter:
    def __init__(self, transport: Optional[Callable] = None, logger=None,
                 call_limit: Optional[int] = None):
        self.api_key = config.ANTHROPIC_API_KEY
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
    def _call(self, system: str, prompt: str) -> dict:
        if not self.enabled:
            raise WriterDisabled("Claude writer disabled (no ANTHROPIC_API_KEY / transport)")
        if self._calls >= self.call_limit:
            raise WriterBudgetExceeded(f"model call limit {self.call_limit} reached")
        self._calls += 1
        if self.logger:
            self.logger.info("model_call", model=config.CLAUDE_MODEL, n=self._calls,
                             cap=self.call_limit)
        # Rate-limit guard: space calls out to avoid 429s.
        if self._calls > 1:
            time.sleep(2)

        if self._transport is not None:
            return self._transport(system, prompt)

        url = f"{config.ANTHROPIC_API_BASE}/v1/messages"
        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 300,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        return post_json(url, payload, headers=headers)

    @staticmethod
    def _extract_json(resp: dict) -> dict:
        """Extract JSON from Claude's response.
        Claude returns: {"content": [{"type": "text", "text": "..."}], ...}
        """
        try:
            text = resp["content"][0]["text"]
            # Strip markdown code fences if present
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                # Remove first line (```json or ```) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()
            return json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            # Test transports may return the parsed dict directly.
            if isinstance(resp, dict) and ("body" in resp or "text" in resp):
                return resp
            raise

    def write_briefing(self, cand: Candidate, lane: str = "") -> Optional[Briefing]:
        """Return a source-bound Briefing, or None on failure (fail safe)."""
        try:
            resp = self._call(_BRIEFING_SYSTEM, self.build_briefing_prompt(cand))
            data = self._extract_json(resp)
        except (WriterDisabled, WriterBudgetExceeded):
            raise
        except Exception as e:
            print(f"    [writer] briefing FAILED for '{cand.title[:60]}': "
                  f"{type(e).__name__}: {e}")
            resp_preview = str(resp)[:300] if 'resp' in dir() else "no response"
            print(f"    [writer] response preview: {resp_preview}")
            if self.logger:
                self.logger.warning("briefing_gen_failed", url=cand.url,
                                    error=str(e)[:120])
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
            resp = self._call(_QUICK_HIT_SYSTEM, self.build_quick_hit_prompt(cand))
            data = self._extract_json(resp)
        except (WriterDisabled, WriterBudgetExceeded):
            raise
        except Exception as e:
            print(f"    [writer] quick hit FAILED for '{cand.title[:60]}': "
                  f"{type(e).__name__}: {e}")
            resp_preview = str(resp)[:300] if 'resp' in dir() else "no response"
            print(f"    [writer] response preview: {resp_preview}")
            if self.logger:
                self.logger.warning("quick_hit_gen_failed", url=cand.url,
                                    error=str(e)[:120])
            return None
        return QuickHit(
            text=data.get("text", ""), lane=lane,
            source=Source(url=cand.url, title=cand.title, publisher=cand.publisher,
                          published=cand.published, free_access=True),
        )
