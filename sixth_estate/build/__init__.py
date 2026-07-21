"""Edition assembly helpers — build data boxes, voice blocks, and full editions.

These are pure constructors that take schema objects and return schema objects.
No network calls. Used by the pipeline, make_sample_edition, and tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .. import config
from ..schema import (Closer, DataBox, DataMetric, Edition, Receipt, Source,
                      VoiceBlock)


def build_money_box(
    equities: list[DataMetric] | None = None,
    treasury: DataMetric | None = None,
    mortgage: DataMetric | None = None,
    crypto: list[DataMetric] | None = None,
    cpi: DataMetric | None = None,
) -> DataBox:
    """Assemble the Money Box from individual data metrics."""
    metrics: list[DataMetric] = []
    if equities:
        metrics.extend(equities)
    if treasury:
        metrics.append(treasury)
    if mortgage:
        metrics.append(mortgage)
    if crypto:
        metrics.extend(crypto)
    if cpi:
        metrics.append(cpi)
    return DataBox(kind="money", title="Money Box", metrics=metrics)


def build_sports_box(
    scores: list[DataMetric] | None = None,
) -> DataBox:
    """Assemble the Sports Box from league scores."""
    return DataBox(kind="sports", title="Sports Box",
                   metrics=list(scores or []))


def build_scoreboard_weather_box(
    scores: list[DataMetric] | None = None,
    weather: list[DataMetric] | None = None,
) -> DataBox:
    """Legacy builder kept for test compatibility. New editions use
    build_sports_box (no weather)."""
    metrics: list[DataMetric] = []
    if scores:
        metrics.extend(scores)
    if weather:
        metrics.extend(weather)
    return DataBox(kind="scoreboard_weather", title="Scoreboard + Weather",
                   metrics=metrics)


def build_this_day(vb: VoiceBlock) -> VoiceBlock:
    """Pass-through with kind normalization for the This Day voice block."""
    vb.kind = "this_day"
    if not vb.title:
        vb.title = "This Day"
    return vb


def build_the_number(
    metric: DataMetric,
    framing: str = "",
) -> VoiceBlock:
    """Build a 'The Number' voice block from a data metric + editorial framing.
    Retained for test compatibility; not used in new editions."""
    text = framing or f"{metric.value} — {metric.label}"
    return VoiceBlock(
        kind="the_number", title="The Number",
        text=text, as_of=metric.as_of,
        source=metric.source,
    )


def assemble_edition(
    date: str,
    briefings,
    quick_hits,
    data_boxes,
    voice_blocks,
    closer: Optional[Closer],
    receipt: Optional[Receipt] = None,
    demo: bool = False,
    extra_meta: dict | None = None,
) -> Edition:
    """Combine all sections into a complete Edition object."""
    nb = len(list(briefings))
    nq = len(list(quick_hits))
    meta = {
        "brand": config.BRAND,
        "structure": f"{nb}+{nq}+{len(list(data_boxes))}+"
                     f"{len(list(voice_blocks))}+{config.N_CLOSERS}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra_meta:
        meta.update(extra_meta)
    return Edition(
        date=date,
        briefings=list(briefings),
        quick_hits=list(quick_hits),
        data_boxes=list(data_boxes),
        voice_blocks=list(voice_blocks),
        closer=closer,
        receipt=receipt,
        meta=meta,
        demo=demo,
    )
