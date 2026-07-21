"""Structured edition schema for THE 6th ESTATE.

Canonical daily structure — 4 + 5 + 2 + 2 + 1 = 14 items:
  * 4 Briefings   (60-75 words each, exact source links)
  * 5 Quick Hits  (<=25 words each, one exact free-access source each)
  * 2 Data Boxes  (Money Box; Scoreboard + Weather) — sourced, timestamped
  * 2 Voice Blocks (This Day; The Number) — sourced
  * 1 Closer      (quote / curiosity / et-cetera; sourced when factual)

Plain dataclasses (stdlib only) with to_dict/from_dict so editions serialize to
JSON with no third-party dependency. The JSON on disk is the single interchange
format used by validators, the site generator, and the email builder.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Source:
    """A single citation. `url` must be a direct article/document/dataset link.
    `free_access` marks reader-accessible destinations; never set True for a
    paywalled page."""
    url: str
    title: str = ""
    publisher: str = ""
    published: str = ""       # ISO date of the source item, if known
    free_access: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Any) -> "Source":
        if isinstance(d, str):
            return cls(url=d)
        d = dict(d or {})
        return cls(
            url=d.get("url") or d.get("href") or "",
            title=d.get("title", ""),
            publisher=d.get("publisher", ""),
            published=d.get("published", ""),
            free_access=bool(d.get("free_access", True)),
        )


@dataclass
class Briefing:
    """A 60-75 word briefing. `why_it_matters` is required for the Money &
    Markets lane and optional elsewhere."""
    headline: str
    body: str
    sources: list[Source] = field(default_factory=list)
    lane: str = ""
    why_it_matters: str = ""
    high_risk: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sources"] = [s.to_dict() for s in self.sources]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Briefing":
        d = dict(d or {})
        return cls(
            headline=d.get("headline", ""),
            body=d.get("body", ""),
            sources=[Source.from_dict(s) for s in d.get("sources", [])],
            lane=d.get("lane", ""),
            why_it_matters=d.get("why_it_matters", ""),
            high_risk=bool(d.get("high_risk", False)),
        )


@dataclass
class QuickHit:
    """A <=25 word quick hit with exactly one exact free-access source."""
    text: str
    source: Optional[Source] = None
    lane: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source.to_dict() if self.source else None,
            "lane": self.lane,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QuickHit":
        d = dict(d or {})
        src = d.get("source")
        return cls(
            text=d.get("text", ""),
            source=Source.from_dict(src) if src else None,
            lane=d.get("lane", ""),
        )


@dataclass
class DataMetric:
    """One labelled value inside a data box, with its own source + as-of stamp."""
    label: str
    value: str
    source: Optional[Source] = None
    as_of: str = ""

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "value": self.value,
            "source": self.source.to_dict() if self.source else None,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DataMetric":
        d = dict(d or {})
        src = d.get("source")
        return cls(
            label=d.get("label", ""),
            value=d.get("value", ""),
            source=Source.from_dict(src) if src else None,
            as_of=d.get("as_of", ""),
        )


@dataclass
class DataBox:
    """A data box (e.g. 'Money Box' or 'Scoreboard + Weather'). Every metric must
    carry a source and an as-of timestamp."""
    kind: str        # "money" | "scoreboard_weather"
    title: str
    metrics: list[DataMetric] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title,
                "metrics": [m.to_dict() for m in self.metrics]}

    @classmethod
    def from_dict(cls, d: dict) -> "DataBox":
        d = dict(d or {})
        return cls(
            kind=d.get("kind", ""),
            title=d.get("title", ""),
            metrics=[DataMetric.from_dict(m) for m in d.get("metrics", [])],
        )


@dataclass
class VoiceBlock:
    """A voice block: 'This Day' (Wikipedia On This Day) or 'The Number' (one
    sourced statistic)."""
    kind: str        # "this_day" | "the_number"
    title: str
    text: str
    source: Optional[Source] = None
    as_of: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "text": self.text,
            "source": self.source.to_dict() if self.source else None,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceBlock":
        d = dict(d or {})
        src = d.get("source")
        return cls(
            kind=d.get("kind", ""),
            title=d.get("title", ""),
            text=d.get("text", ""),
            source=Source.from_dict(src) if src else None,
            as_of=d.get("as_of", ""),
        )


@dataclass
class Closer:
    """The closer: a quote, curiosity, or one-sentence et-cetera. `factual` marks
    whether a source is required."""
    text: str
    kind: str = "quote"      # "quote" | "curiosity" | "et_cetera"
    attribution: str = ""
    factual: bool = False
    source: Optional[Source] = None

    def to_dict(self) -> dict:
        return {
            "text": self.text, "kind": self.kind, "attribution": self.attribution,
            "factual": self.factual,
            "source": self.source.to_dict() if self.source else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Closer":
        d = dict(d or {})
        src = d.get("source")
        return cls(
            text=d.get("text", ""),
            kind=d.get("kind", "quote"),
            attribution=d.get("attribution", ""),
            factual=bool(d.get("factual", False)),
            source=Source.from_dict(src) if src else None,
        )


@dataclass
class Edition:
    date: str                                   # YYYY-MM-DD
    briefings: list[Briefing] = field(default_factory=list)
    quick_hits: list[QuickHit] = field(default_factory=list)
    data_boxes: list[DataBox] = field(default_factory=list)
    voice_blocks: list[VoiceBlock] = field(default_factory=list)
    closer: Optional[Closer] = None
    meta: dict = field(default_factory=dict)
    demo: bool = False                          # True for fixture/demo editions

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "demo": self.demo,
            "briefings": [b.to_dict() for b in self.briefings],
            "quick_hits": [q.to_dict() for q in self.quick_hits],
            "data_boxes": [x.to_dict() for x in self.data_boxes],
            "voice_blocks": [v.to_dict() for v in self.voice_blocks],
            "closer": self.closer.to_dict() if self.closer else None,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edition":
        d = dict(d or {})
        closer = d.get("closer")
        return cls(
            date=d.get("date", ""),
            demo=bool(d.get("demo", False)),
            briefings=[Briefing.from_dict(b) for b in d.get("briefings", [])],
            quick_hits=[QuickHit.from_dict(q) for q in d.get("quick_hits", [])],
            data_boxes=[DataBox.from_dict(x) for x in d.get("data_boxes", [])],
            voice_blocks=[VoiceBlock.from_dict(v) for v in d.get("voice_blocks", [])],
            closer=Closer.from_dict(closer) if closer else None,
            meta=d.get("meta", {}),
        )

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: Path) -> "Edition":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def all_sources(self) -> list[Source]:
        out: list[Source] = []
        for b in self.briefings:
            out.extend(b.sources)
        for q in self.quick_hits:
            if q.source:
                out.append(q.source)
        for box in self.data_boxes:
            for m in box.metrics:
                if m.source:
                    out.append(m.source)
        for v in self.voice_blocks:
            if v.source:
                out.append(v.source)
        if self.closer and self.closer.source:
            out.append(self.closer.source)
        return out
