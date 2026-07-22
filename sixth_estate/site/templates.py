"""HTML fragments for the static site. Pure string builders — no I/O.

Reuses the existing 6E design tokens in site/assets/css/style.css (paper/ink/
accent palette, Instrument Serif + DM Sans). The 4+5+2+2+1 hierarchy is made
visually explicit with numbered section rails.
"""
from __future__ import annotations

import html
from typing import Optional

from .. import config
from ..schema import Briefing, Closer, DataBox, Edition, QuickHit, Receipt, Source, VoiceBlock

# Navigation targets are RELATIVE (no leading slash) so pages resolve correctly
# both at the site root on Netlify and under a nested/proxied preview host. The
# per-page `depth` supplies the right number of "../" hops (see rel_prefix).
NAV = [
    ("index.html", "Home"),
    ("today.html", "Today"),
    ("archive.html", "Archive"),
    ("corrections.html", "Corrections"),
    ("manifesto.html", "Manifesto"),
    ("subscribe.html", "Subscribe"),
    ("advertise.html", "Advertise"),
]


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def rel_prefix(depth: int) -> str:
    """Relative hop from a page `depth` directories below the site root back to
    the root. Root pages -> "" ; editions/ pages (depth 1) -> "../"."""
    return "../" * max(0, depth)


def page(title: str, body: str, description: str = "", canonical_path: str = "/",
         depth: int = 0) -> str:
    desc = description or config.TAGLINE
    canonical = config.CANONICAL_BASE_URL + canonical_path
    pre = rel_prefix(depth)
    nav = "".join(f'<a href="{esc(pre + href)}">{esc(label)}</a>' for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">
  <link rel="canonical" href="{esc(canonical)}">
  <link rel="icon" type="image/svg+xml" href="{esc(pre)}assets/favicon.svg">
  <meta property="og:site_name" content="{esc(config.BRAND)}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(desc)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{esc(canonical)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{esc(pre)}assets/css/style.css">
  <link rel="stylesheet" href="{esc(pre)}assets/css/edition.css">
</head>
<body>
  <header class="site-header">
    <a class="brand-lockup" href="{esc(pre)}index.html">{esc(config.BRAND)}</a>
    <nav class="site-nav">{nav}</nav>
  </header>
  <main class="site-main">
{body}
  </main>
  <footer class="site-footer">
    <p>{esc(config.BRAND)} — {esc(config.TAGLINE)}</p>
    <p class="muted">{esc(config.PUBLISHER)} · Editor: {esc(config.EDITOR)}</p>
    <p class="muted"><a href="{esc(pre)}corrections.html">Corrections</a> · <a href="{esc(pre)}manifesto.html">Manifesto</a> · <a href="{esc(pre)}subscribe.html">Subscribe</a> · <a href="{esc(pre)}advertise.html">Advertise</a></p>
    <p class="muted">Also from Pitre Media: <a href="https://thedailydrumbeat.com" rel="noopener" target="_blank">The Daily Drumbeat</a></p>
  </footer>
</body>
</html>"""


def _sources_html(sources: list[Source]) -> str:
    if not sources:
        return ""
    links = []
    for s in sources:
        label = esc(s.publisher or s.title or s.url)
        links.append(f'<a class="src" href="{esc(s.url)}" rel="nofollow noopener" target="_blank">{label}</a>')
    return '<div class="sources">Sources: ' + " · ".join(links) + "</div>"


def _one_source_html(s: Optional[Source]) -> str:
    if not s or not s.url:
        return ""
    label = esc(s.publisher or s.title or s.url)
    return f'<a class="src" href="{esc(s.url)}" rel="nofollow noopener" target="_blank">{label}</a>'


def section_rail(number: int, name: str, count_label: str) -> str:
    return (f'<div class="rail"><span class="rail-num">{number}</span>'
            f'<span class="rail-name">{esc(name)}</span>'
            f'<span class="rail-count">{esc(count_label)}</span></div>')


def _copy_link_btn(headline: str) -> str:
    """Inline Copy Link button with branded share text."""
    safe = esc(headline).replace("'", "\\'").replace('"', "&quot;")
    return (f'<button class="copy-link-btn" data-headline="{safe}" '
            f'onclick="copyArticleLink(this)" title="Copy link">'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
            f'<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
            f' Copy link</button>')


def briefing_html(b: Briefing, idx: int) -> str:
    wim = (f'<p class="why"><strong>Why it matters:</strong> {esc(b.why_it_matters)}</p>'
           if b.why_it_matters else "")
    lane = f'<span class="lane">{esc(b.lane)}</span>' if b.lane else ""
    copy_btn = _copy_link_btn(b.headline)
    return f"""<article class="briefing">
  <div class="briefing-head">{lane}</div>
  <h3>{esc(b.headline)}</h3>
  <p>{esc(b.body)}</p>
  {wim}
  <div class="briefing-foot">
    {_sources_html(b.sources)}
    {copy_btn}
  </div>
</article>"""


def quick_hit_html(q: QuickHit) -> str:
    lane = f'<span class="lane">{esc(q.lane)}</span>' if q.lane else ""
    copy_btn = _copy_link_btn(q.text[:60])
    return f"""<li class="quick-hit">{lane}<span class="qh-text">{esc(q.text)}</span>
  <div class="qh-foot">{_one_source_html(q.source)} {copy_btn}</div></li>"""


def data_box_html(box: DataBox) -> str:
    # Skip rendering entirely if the box has no metrics (avoids empty white space).
    if not box.metrics:
        return ""

    # Sports Box: split quick-hit items (editorial) from score items.
    if box.kind == "sports":
        sports_hits = [m for m in box.metrics if m.as_of == "quick_hit"]
        scores = [m for m in box.metrics if m.as_of != "quick_hit"]

        hits_html = ""
        if sports_hits:
            items = "".join(
                f'<li class="sports-hit">{esc(m.label)}: {esc(m.value)} '
                f'{_one_source_html(m.source)}</li>'
                for m in sports_hits
            )
            hits_html = f'<ul class="sports-hits">{items}</ul>'

        if not scores and not sports_hits:
            return ""

        rows = ""
        if scores:
            rows = "".join(
                f'<tr><th>{esc(m.label)}</th><td>{esc(m.value)}</td>'
                f'<td class="asof">{esc(m.as_of)}</td>'
                f'<td class="src-cell">{_one_source_html(m.source)}</td></tr>'
                for m in scores
            )
            rows = (f'<table class="data-table"><thead><tr><th>Metric</th><th>Value</th>'
                    f'<th>As of</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>')

        return f"""<div class="data-box">
  <h4>{esc(box.title)}</h4>
  {hits_html}
  {rows}
</div>"""

    # Default data box rendering (Money Box etc.)
    rows = "".join(
        f'<tr><th>{esc(m.label)}</th><td>{esc(m.value)}</td>'
        f'<td class="asof">{esc(m.as_of)}</td>'
        f'<td class="src-cell">{_one_source_html(m.source)}</td></tr>'
        for m in box.metrics
    )
    return f"""<div class="data-box">
  <h4>{esc(box.title)}</h4>
  <table class="data-table"><thead><tr><th>Metric</th><th>Value</th><th>As of</th><th>Source</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>"""


def voice_block_html(v: VoiceBlock) -> str:
    asof = f'<span class="asof">{esc(v.as_of)}</span>' if v.as_of else ""
    return f"""<div class="voice-block">
  <h4>{esc(v.title)} {asof}</h4>
  <p>{esc(v.text)}</p>
  {_one_source_html(v.source)}
</div>"""


def closer_html(c: Closer) -> str:
    attribution = f'<footer>— {esc(c.attribution)}</footer>' if c.attribution else ""
    src = _one_source_html(c.source) if c.factual else ""
    return f"""<blockquote class="closer closer--centered">
  <p>{esc(c.text)}</p>
  {attribution}
  {src}
</blockquote>"""


def receipt_html(r: Receipt) -> str:
    src = _one_source_html(r.source) if r.source else ""
    return f"""<div class="receipt">
  <h4>The Receipt</h4>
  <p class="receipt-claim"><strong>The claim:</strong> {esc(r.title)}</p>
  <p class="receipt-evidence"><strong>The evidence:</strong> {esc(r.description)}</p>
  <p class="receipt-link"><strong>Read it yourself:</strong> {src}</p>
</div>"""


def edition_body(ed: Edition) -> str:
    demo_banner = (
        '<div class="demo-banner">DEMO EDITION — sample/fixture data, not real '
        'current news. For layout and QA only.</div>' if ed.demo else "")
    briefings = "".join(briefing_html(b, i) for i, b in enumerate(ed.briefings))
    quick_hits = "".join(quick_hit_html(q) for q in ed.quick_hits)
    data_boxes = "".join(data_box_html(x) for x in ed.data_boxes)
    voice_blocks = "".join(voice_block_html(v) for v in ed.voice_blocks)
    closer = closer_html(ed.closer) if ed.closer else ""
    receipt_block = receipt_html(ed.receipt) if ed.receipt else ""
    date_readable = ed.meta.get("date_readable", ed.date)
    nb = len(ed.briefings)
    nq = len(ed.quick_hits)

    sections = f"""
      <section class="sec sec-briefings">
        {section_rail(1, "Briefings", str(nb))}
        {briefings}
      </section>

      <section class="sec sec-quick-hits">
        {section_rail(2, "Quick Hits", str(nq))}
        <ul class="quick-hits">{quick_hits}</ul>
      </section>

      <section class="sec sec-data">
        {section_rail(3, "Data", str(len(ed.data_boxes)))}
        <div class="data-grid">{data_boxes}</div>
      </section>"""

    if ed.voice_blocks:
        sections += f"""
      <section class="sec sec-voice">
        {section_rail(4, "This Day", "")}
        <div class="voice-grid">{voice_blocks}</div>
      </section>"""

    rail_n = 5 if ed.voice_blocks else 4
    if ed.receipt:
        sections += f"""
      <section class="sec sec-receipt">
        {section_rail(rail_n, "The Receipt", "")}
        {receipt_block}
      </section>"""
        rail_n += 1

    sections += f"""
      <section class="sec sec-closer">
        {section_rail(rail_n, "The Closer", "")}
        {closer}
      </section>"""

    share_runner = f"""
      <div class="share-runner">
        <span>Share</span> <a href="{esc(config.CANONICAL_BASE_URL)}" class="share-runner-link">{esc(config.CANONICAL_DOMAIN)}</a>
        <button class="copy-link-btn" onclick="copySiteLink()" title="Copy link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          Copy
        </button>
      </div>"""

    copy_js = """
      <script>
      function copyArticleLink(btn){
        var h=btn.getAttribute('data-headline');
        var t=h+' — via """ + config.CANONICAL_BASE_URL + """';
        navigator.clipboard.writeText(t).then(function(){
          btn.textContent='Copied!';setTimeout(function(){btn.innerHTML='<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71\"/><path d=\"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71\"/></svg> Copy link';},1500);
        });
      }
      function copySiteLink(){
        navigator.clipboard.writeText('""" + config.CANONICAL_BASE_URL + """').then(function(){
          var b=document.querySelector('.share-runner .copy-link-btn');
          if(b){b.textContent='Copied!';setTimeout(function(){b.innerHTML='<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71\"/><path d=\"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71\"/></svg> Copy';},1500);}
        });
      }
      </script>"""

    return f"""
    <article class="edition">
      {demo_banner}
      <div class="edition-masthead">
        <p class="kicker">{esc(config.BRAND)}</p>
        <h1>Daily Edition</h1>
        <p class="edition-date">{esc(date_readable)}</p>
      </div>
      {sections}
      {share_runner}
    </article>
    {copy_js}
"""
