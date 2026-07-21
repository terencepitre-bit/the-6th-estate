"""Tiny stdlib HTTP helper (no third-party deps).

All outbound network access in this package funnels through `get_json` / `get_text`.
Tests never call these — external services are injected as fakes instead. Secrets
passed in headers are never logged.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, detail: str = ""):
        super().__init__(f"HTTP {status} for {url}: {detail}"[:300])
        self.status = status
        self.url = url


def get_text(url: str, headers: Optional[dict] = None, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "6E-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, url, e.reason if isinstance(e.reason, str) else "") from e
    except urllib.error.URLError as e:
        raise HttpError(0, url, str(e.reason)) from e


def get_json(url: str, headers: Optional[dict] = None, timeout: int = 20):
    return json.loads(get_text(url, headers=headers, timeout=timeout))
