"""Brevo-ready email HTML from a structured Edition, plus a strictly-gated sender.

BUILDING HTML is always safe and offline. SENDING is gated behind THREE
independent guards, all of which must be satisfied:
  1. explicit `send=True` argument (a --send CLI flag),
  2. config.EMAIL_ENABLED (SIXTHE_EMAIL_ENABLED=1),
  3. a proxied Brevo credential provided via `transport`/credential handle.
Idempotency is enforced by EditionState: a repeated send is a no-op.

The Brevo v3 credential is injected by a secure proxy as the `api-key` header;
this module never reads, stores, or logs a raw key. `transport` is injectable so
tests verify payload shape with zero network calls.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Callable, Optional

from .. import config
from ..schema import Edition, Source
from ..state import EditionState


class EmailSendDisabled(RuntimeError):
    pass


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _src_line(sources: list[Source]) -> str:
    if not sources:
        return ""
    parts = [f'<a href="{_esc(s.url)}" style="color:#8B1A1A">{_esc(s.publisher or s.title or "source")}</a>'
             for s in sources if s and s.url]
    return f'<div style="font-size:12px;color:#5C5A54">Sources: {" · ".join(parts)}</div>' if parts else ""


def build_email_html(ed: Edition) -> str:
    """Return responsive, inline-styled HTML for the edition email."""
    url = f"{config.CANONICAL_BASE_URL}/editions/{ed.date}.html"
    demo = ('<p style="background:#F5E4E4;color:#8B1A1A;padding:8px;font-weight:bold">'
            'DEMO EDITION — sample data, not real current news.</p>' if ed.demo else "")

    def briefing(b):
        wim = (f'<p style="background:#EDE4CE;padding:6px;font-size:14px"><b>Why it matters:</b> {_esc(b.why_it_matters)}</p>'
               if b.why_it_matters else "")
        return (f'<tr><td style="padding:8px 0;border-bottom:1px solid #C9C4B7">'
                f'<h3 style="font-family:Georgia,serif;margin:0 0 4px">{_esc(b.headline)}</h3>'
                f'<p style="margin:0 0 4px">{_esc(b.body)}</p>{wim}{_src_line(b.sources)}</td></tr>')

    def quick_hit(q):
        s = _src_line([q.source]) if q.source else ""
        return (f'<li style="margin-bottom:6px;border-left:3px solid #B8860B;padding-left:8px">'
                f'{_esc(q.text)} {s}</li>')

    def data_box(box):
        rows = "".join(
            f'<tr><td style="padding:2px 6px;border-bottom:1px solid #eee"><b>{_esc(m.label)}</b></td>'
            f'<td style="padding:2px 6px;border-bottom:1px solid #eee">{_esc(m.value)}</td>'
            f'<td style="padding:2px 6px;border-bottom:1px solid #eee;font-size:11px;color:#5C5A54">{_esc(m.as_of)}</td></tr>'
            for m in box.metrics)
        return (f'<div style="border:1px solid #C9C4B7;padding:10px;margin-bottom:10px">'
                f'<h4 style="font-family:Georgia,serif;margin:0 0 6px">{_esc(box.title)}</h4>'
                f'<table style="width:100%;border-collapse:collapse;font-size:13px">{rows}</table></div>')

    def voice(v):
        return (f'<div style="border:1px solid #C9C4B7;padding:10px;margin-bottom:10px">'
                f'<h4 style="font-family:Georgia,serif;margin:0 0 6px">{_esc(v.title)} '
                f'<span style="font-size:11px;color:#5C5A54">{_esc(v.as_of)}</span></h4>'
                f'<p style="margin:0">{_esc(v.text)}</p>{_src_line([v.source]) if v.source else ""}</div>')

    briefings = "".join(briefing(b) for b in ed.briefings)
    quick_hits = "".join(quick_hit(q) for q in ed.quick_hits)
    data_boxes = "".join(data_box(x) for x in ed.data_boxes)
    voices = "".join(voice(v) for v in ed.voice_blocks)
    closer = ""
    if ed.closer:
        c_src = _src_line([ed.closer.source]) if (ed.closer.factual and ed.closer.source) else ""
        attribution = f'<footer style="font-size:13px;color:#5C5A54">— {_esc(ed.closer.attribution)}</footer>' if ed.closer.attribution else ""
        closer = (f'<blockquote style="font-family:Georgia,serif;font-style:italic;'
                  f'border-left:4px solid #8B1A1A;padding:6px 14px;margin:0">'
                  f'{_esc(ed.closer.text)}{attribution}{c_src}</blockquote>')

    date_readable = ed.meta.get("date_readable", ed.date)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#FAF7F0;color:#111;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FAF7F0"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;padding:20px">
  <tr><td style="text-align:center;border-bottom:3px double #C9C4B7;padding-bottom:12px">
    <div style="letter-spacing:.18em;text-transform:uppercase;font-size:11px;color:#8B1A1A">{_esc(config.BRAND)}</div>
    <h1 style="font-family:Georgia,serif;margin:6px 0">Daily Edition</h1>
    <div style="color:#5C5A54;font-size:14px">{_esc(date_readable)}</div>
  </td></tr>
  <tr><td style="padding-top:12px">{demo}</td></tr>
  <tr><td><h2 style="font-family:Georgia,serif;border-bottom:2px solid #8B1A1A">1 · Briefings</h2>
    <table role="presentation" width="100%">{briefings}</table></td></tr>
  <tr><td><h2 style="font-family:Georgia,serif;border-bottom:2px solid #8B1A1A">2 · Quick Hits</h2>
    <ul style="padding-left:0;list-style:none">{quick_hits}</ul></td></tr>
  <tr><td><h2 style="font-family:Georgia,serif;border-bottom:2px solid #8B1A1A">3 · Data Boxes</h2>{data_boxes}</td></tr>
  <tr><td><h2 style="font-family:Georgia,serif;border-bottom:2px solid #8B1A1A">4 · Voice Blocks</h2>{voices}</td></tr>
  <tr><td><h2 style="font-family:Georgia,serif;border-bottom:2px solid #8B1A1A">5 · The Closer</h2>{closer}</td></tr>
  <tr><td style="text-align:center;padding:16px 0">
    <a href="{_esc(url)}" style="background:#8B1A1A;color:#fff;padding:10px 20px;text-decoration:none">Read on the web</a></td></tr>
  <tr><td style="border-top:1px solid #C9C4B7;padding-top:12px;text-align:center;font-size:12px;color:#5C5A54">
    {_esc(config.BRAND)} — {_esc(config.TAGLINE)}<br>{_esc(config.PUBLISHER)}<br>
    <a href="{{{{ unsubscribe }}}}" style="color:#5C5A54">Unsubscribe</a>
  </td></tr>
</table></td></tr></table></body></html>"""


def build_campaign_payload(ed: Edition, html_content: str) -> dict:
    """Brevo v3 'create email campaign' payload (createdCampaign → sendNow)."""
    date_readable = ed.meta.get("date_readable", ed.date)
    return {
        "name": f"6E Daily {ed.date}",
        "subject": f"{config.BRAND} — {date_readable}",
        "sender": {"name": config.BREVO_SENDER_NAME, "email": config.BREVO_SENDER_EMAIL},
        "replyTo": config.BREVO_REPLY_TO,
        "htmlContent": html_content,
        "recipients": {"listIds": [config.BREVO_LIST_ID]},
    }


def send_edition(ed: Edition, state: EditionState, *, send: bool = False,
                 transport: Optional[Callable] = None) -> dict:
    """Gated send. Returns a result dict. Never sends unless all guards pass.

    `transport(payload)->{"id": campaign_id}` stands in for the proxied Brevo
    call so no raw credential is handled here and tests stay offline.
    """
    html_content = build_email_html(ed)
    if not send:
        return {"sent": False, "reason": "send flag not set (dry-run)",
                "html_bytes": len(html_content)}
    if not config.EMAIL_ENABLED:
        raise EmailSendDisabled("SIXTHE_EMAIL_ENABLED is not set; refusing to send")
    if transport is None:
        raise EmailSendDisabled("No Brevo credential/transport provided; refusing to send")
    if state.emailed:
        return {"sent": False, "reason": "already emailed (idempotent no-op)",
                "campaign_id": state.email_campaign_id}

    payload = build_campaign_payload(ed, html_content)
    resp = transport(payload)
    campaign_id = resp.get("id") if isinstance(resp, dict) else None
    when = datetime.now(timezone.utc).isoformat()
    state.mark_emailed(when, campaign_id)
    return {"sent": True, "campaign_id": campaign_id, "at": when}
