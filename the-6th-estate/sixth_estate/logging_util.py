"""Structured per-edition logger. Writes JSON lines to logs/<date>.log.

NEVER logs secrets: callers pass only counts, ids, and outcomes. A defensive
redactor drops any field whose name hints at a credential.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config

_SECRET_HINTS = ("key", "token", "secret", "password", "credential", "authorization")


def _redact(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if any(h in k.lower() for h in _SECRET_HINTS):
            out[k] = "***redacted***"
        else:
            out[k] = v
    return out


class EditionLogger:
    def __init__(self, date: str, to_file: bool = True):
        self.date = date
        self.records: list[dict] = []
        self.path = config.LOGS_DIR / f"{date}.log" if to_file else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, level: str, event: str, **fields):
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "level": level,
               "event": event, **_redact(fields)}
        self.records.append(rec)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(rec) + "\n")

    def info(self, event: str, **f):
        self._emit("info", event, **f)

    def warning(self, event: str, **f):
        self._emit("warning", event, **f)

    def error(self, event: str, **f):
        self._emit("error", event, **f)
