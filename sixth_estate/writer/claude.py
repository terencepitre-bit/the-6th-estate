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
    "You are a sharp wire editor for THE 6th ESTATE, a daily US newsletter. "
    "Summarize ONLY the supplied source text. Never add facts, names, quotes, "
    "or URLs not present in the sources. "
    "VOICE: Declarative and direct. State what happened: 'Apple announced', "
    "'The Fed cut', 'Verizon signed'. Use past or present tense for events that "
    "occurred. Reserve 'could' or 'may' ONLY for genuinely unresolved future "
    "outcomes — never as hedging on facts the source states plainly. Banned "
    "hedges: 'could help', 'may support', 'suggesting that', 'according to "
    "research into', 'experts point to'. If the source says it happened, say it "
    "happened. "
    "HEADLINE: 6-11 words, active verb, specific. Lead with the actor or the "
    "number. Build in the stakes. A touch of wit is welcome when the story "
    "allows it, but never at the expense of clarity, and never punny on tragic "
    "news. Bad: 'Play-Based Early Childhood Programs Build Skills That Last'. "
    "Good: 'Verizon Signs $1B Google Fiber Deal, Wants More'. "
    "BODY: 60-75 words, factual, non-editorial, concrete numbers and names first. "
    "WHY IT MATTERS: One standalone sentence on real-world impact for readers — "
    "their money, health, kids, home, or community — not a restatement of the "
    "headline. "
    "Do NOT include parenthetical notes, meta-instructions, or guidance text in "
    "any field. Every field must read as clean, publishable prose. "
    "Return ONLY a JSON object with keys: headline, body, why_it_matters. "
    "No markdown, no code fences, no preamble."
)
_QUICK_HIT_SYSTEM = (
    "You are a sharp wire editor for THE 6th ESTATE. Compress the supplied source "
    "into a single declarative sentence of 25 words or fewer. State what "
    "happened — no hedging, no 'could' or 'may' unless the outcome is genuinely "
    "undecided. Include a specific number, name, or concrete detail. Complete "
    "sentence, not a fragment or bare headline. No opinion, no added facts, no "
    "URLs. "
    "Return ONLY a JSON object with key: text. "
    "No markdown, no code fences, no preamble."
)
_BY_THE_WAY_SYSTEM = (
    "You are writing a one-liner for 'By the Way', the light closing section of "
    "THE 6th ESTATE — quirky, surprising, or delightful smaller stories. "
    "Compress the supplied source into ONE sentence of 18 words or fewer. "
    "Declarative and playful, but strictly factual: use only what the source "
    "says. Lead with the surprising detail. No opinion, no added facts, no URLs, "
    "no exclamation points. "
    "Return ONLY a JSON object with key: text. "
    "No markdown, no code fences, no preamble."
)
_COLD_OPEN_SYSTEM = (
    "You write the opening lines of THE 6th ESTATE, a daily US morning "
    "newsletter. Given today's date and a list of story headlines, write a warm, "
    "confident 2-3 sentence cold open. "
    "Sentence 1: 'Good morning, it's {weekday}, {month} {day}.' followed in the "
    "same sentence by a light, intriguing nod to ONE story from the list — "
    "ideally the most surprising or human one. "
    "Then one more sentence teasing 1-2 OTHER stories from the list, naming "
    "their topic areas naturally. "
    "Tone: 1440 / Morning Brew — smart, brisk, friendly, never jokey about "
    "tragedy. Use ONLY the supplied headlines; never invent stories. Total "
    "under 55 words. "
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

    def write_by_the_way(self, cand: Candidate) -> Optional[QuickHit]:
        """One-liner for the 'By the Way' light section. Fail-safe like quick hits."""
        try:
            resp = self._call(_BY_THE_WAY_SYSTEM, self.build_quick_hit_prompt(cand))
            data = self._extract_json(resp)
        except (WriterDisabled, WriterBudgetExceeded):
            raise
        except Exception as e:
            print(f"    [writer] by-the-way FAILED for '{cand.title[:60]}': "
                  f"{type(e).__name__}: {e}")
            if self.logger:
                self.logger.warning("btw_gen_failed", url=cand.url,
                                    error=str(e)[:120])
            return None
        return QuickHit(
            text=data.get("text", ""), lane=config.BY_THE_WAY_LANE,
            source=Source(url=cand.url, title=cand.title, publisher=cand.publisher,
                          published=cand.published, free_access=True),
        )

    def write_cold_open(self, date_readable: str, headlines: list[str]) -> str:
        """Return the cold-open greeting text, or "" on any failure (fail safe)."""
        if not headlines:
            return ""
        listing = "\n".join(f"- {h}" for h in headlines[:12])
        prompt = (f"TODAY'S DATE: {date_readable}\n"
                  f"TODAY'S HEADLINES:\n{listing}\n"
                  "Write the cold open now as JSON: {\"text\":...}.")
        try:
            resp = self._call(_COLD_OPEN_SYSTEM, prompt)
            data = self._extract_json(resp)
            return (data.get("text") or "").strip()
        except (WriterDisabled, WriterBudgetExceeded):
            return ""
        except Exception as e:
            print(f"    [writer] cold open FAILED: {type(e).__name__}: {e}")
            if self.logger:
                self.logger.warning("cold_open_failed", error=str(e)[:120])
            return ""

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
