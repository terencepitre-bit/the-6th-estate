"""Idempotent per-edition state.

Prevents duplicate publishing and duplicate email. State lives in state/<date>.json
and records the workflow status and side-effect receipts. A repeated publish/email
is a no-op once the corresponding flag is already set.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import config

# Workflow statuses.
CURATED = "curated"
PREVIEWED = "previewed"
APPROVED = "approved"
PUBLISHED = "published"
SKIPPED = "skipped"
EDIT_HOLD = "edit_hold"


@dataclass
class EditionState:
    date: str
    status: str = CURATED
    published: bool = False
    published_at: str = ""
    emailed: bool = False
    emailed_at: str = ""
    email_campaign_id: Optional[int] = None
    notes: list[str] = field(default_factory=list)

    def path(self) -> Path:
        return config.STATE_DIR / f"{self.date}.json"

    def save(self) -> Path:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))
        return p

    @classmethod
    def load_or_new(cls, date: str) -> "EditionState":
        p = config.STATE_DIR / f"{date}.json"
        if p.exists():
            return cls(**json.loads(p.read_text()))
        return cls(date=date)

    # ── idempotent transitions ────────────────────────────────────────────────
    def mark_published(self, when: str) -> bool:
        """Return True if this call performed the publish; False if already done."""
        if self.published:
            return False
        self.published = True
        self.published_at = when
        self.status = PUBLISHED
        self.save()
        return True

    def mark_emailed(self, when: str, campaign_id: Optional[int]) -> bool:
        """Return True if this call performed the send; False if already sent."""
        if self.emailed:
            return False
        self.emailed = True
        self.emailed_at = when
        self.email_campaign_id = campaign_id
        self.save()
        return True
