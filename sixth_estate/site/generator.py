"""Static-site generator. Renders the 4+5+2+2+1 edition set + standing pages into
site/ for Netlify. Pure file output; no network. Archive is append-only: existing
edition pages are preserved and re-indexed.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import config
from ..schema import Edition
from . import templates as T


def render_edition_page(ed: Edition) -> str:
    title = f"{config.BRAND} — Daily Edition {ed.date}"
    return T.page(title, T.edition_body(ed),
                  description=config.TAGLINE,
                  canonical_path=f"/editions/{ed.date}.html",
                  depth=1)


def _landing_page(latest: Edition | None) -> str:
    latest_link = (f'<a class="cta" href="editions/{latest.date}.html">Read today\'s edition</a>'
                   if latest else '<a class="cta" href="today.html">Read the latest edition</a>')
    body = f"""
    <section class="lp-hero">
      <span class="lp-eyebrow">Free daily briefing</span>
      <h1 class="lp-headline">{T.esc(config.BRAND)}</h1>
      <p class="lp-subhead">{T.esc(config.TAGLINE)} A neutral daily briefing: briefings with impact, quick hits, money and sports data, and a primary-source receipt — every claim sourced, every link free.</p>
      {latest_link}
    </section>
    <section class="lp-explain">
      <h2>What you get every morning</h2>
      <ol class="lp-structure">
        <li><strong>Briefings</strong> — 60-75 words with impact, exact source links.</li>
        <li><strong>Quick Hits</strong> — 25 words max, one free-access source each.</li>
        <li><strong>Money Box</strong> — equities, Treasury, mortgage, crypto, CPI — sourced and timestamped.</li>
        <li><strong>Sports Box</strong> — MLB, NBA, NFL scores.</li>
        <li><strong>This Day</strong> — what happened on this date in history.</li>
        <li><strong>The Receipt</strong> — a primary-source document: the proof behind the news.</li>
        <li><strong>The Closer</strong> — a quote, curiosity, or et-cetera.</li>
      </ol>
    </section>
    {_signup_form()}
"""
    return T.page(f"{config.BRAND} — {config.TAGLINE}", body,
                  description="A free daily briefing for people who want to understand "
                              "the world, not be told how to feel about it.",
                  canonical_path="/")


def _signup_form(prefix: str = "") -> str:
    # Brevo embedded subscription form — subscribers go to list #11
    # "The 6th Estate - Daily Readers". No API key needed; Brevo handles
    # validation, double opt-in, and GDPR compliance.
    return """
    <section class="lp-signup" id="subscribe">
      <h2>Join the daily readers</h2>
      <iframe width="540" height="305" src="https://1a3e105b.sibforms.com/v2/serve/MUIFALJ-gChtKiUKfyY1JZ4Pi2kbrW0yh7D538p9Co95Fcs1_SULUNqyk9a-M8iRXxZ8zByHaTnFB8NcTgvJ01WSc1v1wAkxLV9rKIE4-aHutuz4mMGGfrf7ax1oif3emTY1uRiJUBc3eVqlLy1IG_hpZcPTF-EJ4ZbHVkL4z8hXpi3t20qxMZsDwwYG6dgk6Nh2pC0GdaX0IPjJlw==" frameborder="0" scrolling="auto" allowfullscreen style="display:block;margin-left:auto;margin-right:auto;max-width:100%"></iframe>
      <p class="lp-form-note">Free. Unsubscribe anytime. We never sell your address.</p>
    </section>
"""


def _today_page(latest: Edition | None) -> str:
    if latest is None:
        body = '<section class="empty"><h1>No edition yet</h1><p>Check back soon.</p></section>'
    else:
        body = T.edition_body(latest)
    return T.page(f"{config.BRAND} — Today", body, canonical_path="/today.html")


def _archive_page(editions: list[Edition]) -> str:
    demo_span = ' <span class="demo-tag">demo</span>'
    items = "".join(
        f'<li><a href="editions/{T.esc(e.date)}.html">{T.esc(e.meta.get("date_readable", e.date))}</a>'
        f'{demo_span if e.demo else ""}</li>'
        for e in editions
    )
    body = f"""
    <section class="archive">
      <h1>Archive</h1>
      <p class="muted">Every past edition, preserved.</p>
      <ul class="archive-list">{items or '<li class="muted">No editions yet.</li>'}</ul>
    </section>
"""
    return T.page(f"{config.BRAND} — Archive", body, canonical_path="/archive.html")


def _corrections_page() -> str:
    body = f"""
    <section class="prose">
      <h1>Corrections</h1>
      <p>{T.esc(config.BRAND)} corrects errors promptly and visibly. When we get
      something wrong, we say so — what was wrong, what is right, and when we fixed it.</p>
      <p>Corrections are cheap to maintain because every claim in an edition links to
      its exact source. To report an error, email
      <a href="mailto:corrections@the6thestate.net">corrections@the6thestate.net</a>.</p>
      <h2>Log</h2>
      <p class="muted">No corrections to date.</p>
    </section>
"""
    return T.page(f"{config.BRAND} — Corrections", body, canonical_path="/corrections.html")


def _manifesto_page() -> str:
    body = f"""
    <section class="prose">
      <h1>Manifesto</h1>
      <p>{T.esc(config.BRAND)} reports facts and explains practical impact. We prefer
      "could" over "should" when consequences are uncertain. No preaching, no invented
      scenes, people, or quotes.</p>
      <p>Every edition carries briefings, quick hits, a money box, a sports box, a
      historical note, and a closer. When a primary-source document is available,
      we include The Receipt — the filing, order, or dataset behind the headline.
      Every claim carries an exact, direct source link — never a homepage, section
      page, or search result. We use only free-access sources and never link
      to paywalled content.</p>
      <p>Edited by {T.esc(config.EDITOR)}. {T.esc(config.PUBLISHER)}.</p>
    </section>
"""
    return T.page(f"{config.BRAND} — Manifesto", body, canonical_path="/manifesto.html")


def _subscribe_page() -> str:
    body = f"""
    <section class="sub-hero">
      <h1>Subscribe</h1>
      <p class="dek">Get {T.esc(config.BRAND)} in your inbox every morning. Free.</p>
    </section>
    {_signup_form()}
"""
    return T.page(f"{config.BRAND} — Subscribe", body, canonical_path="/subscribe.html")


def _advertise_page() -> str:
    body = f"""
    <section class="prose">
      <h1>Advertise</h1>
      <p>{T.esc(config.BRAND)} reaches curious, informed readers every morning.
      Three placement options are available:</p>
      <div class="ad-slots">
        <div class="ad-slot">
          <h2>Main Slot</h2>
          <p>Premium placement within the daily briefings section. Your message
          appears alongside the day's lead stories.</p>
        </div>
        <div class="ad-slot">
          <h2>Money Box Slot</h2>
          <p>Positioned within the Money Box data section — ideal for financial
          services, fintech, and investment brands.</p>
        </div>
        <div class="ad-slot">
          <h2>Runner Slot</h2>
          <p>A persistent banner at the bottom of every edition. High visibility,
          every day.</p>
        </div>
      </div>
      <p>Contact us for rates: <a href="mailto:advertise@the6thestate.net">advertise@the6thestate.net</a></p>
    </section>
"""
    return T.page(f"{config.BRAND} — Advertise", body, canonical_path="/advertise.html")


EDITION_CSS = """/* Edition-specific styles layered on the 6E token stylesheet. */
.site-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;
  padding:.75rem 1.25rem;border-bottom:3px double var(--color-divider);
  position:sticky;top:0;background:var(--color-bg);z-index:10;flex-wrap:wrap}
.brand-lockup{font-family:var(--font-display);font-size:1.5rem;letter-spacing:.02em}
.site-nav{display:flex;gap:1rem;flex-wrap:wrap}
.site-nav a{font-size:var(--text-sm);color:var(--color-text-muted)}
.site-nav a:hover{color:var(--color-accent)}
.site-main{max-width:var(--content-default);margin:0 auto;padding:2rem 1.25rem}
.site-footer{max-width:var(--content-default);margin:3rem auto 2rem;padding:2rem 1.25rem;
  border-top:1px solid var(--color-divider);text-align:center}
.muted{color:var(--color-text-muted);font-size:var(--text-sm)}
.demo-banner{background:var(--receipt-bg);border:1px solid var(--accent);color:var(--accent);
  padding:.6rem 1rem;font-weight:700;font-size:var(--text-sm);text-align:center;margin-bottom:1.5rem}
.demo-tag,.demo-tag{color:var(--accent);font-size:var(--text-xs);text-transform:uppercase;margin-left:.4rem}
.edition-masthead{text-align:center;border-bottom:3px double var(--color-divider);padding-bottom:1.5rem;margin-bottom:2rem}
.edition-masthead .kicker{letter-spacing:.18em;text-transform:uppercase;font-size:var(--text-xs);color:var(--accent)}
.edition-masthead h1{font-family:var(--font-display);font-size:var(--text-2xl)}
.edition-date{color:var(--color-text-muted)}
.edition-structure{font-size:var(--text-sm);color:var(--color-text-muted);font-style:italic}
.sec{margin:2.5rem 0}
.rail{display:flex;align-items:baseline;gap:.6rem;border-bottom:2px solid var(--color-accent);padding-bottom:.35rem;margin-bottom:1rem}
.rail-num{font-family:var(--font-display);font-size:1.6rem;color:var(--color-accent);line-height:1}
.rail-name{font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:var(--text-sm)}
.rail-count{margin-left:auto;font-size:var(--text-xs);color:var(--color-text-muted)}
.briefing{margin-bottom:1.75rem;padding-bottom:1.25rem;border-bottom:1px solid var(--color-divider)}
.briefing h3{font-family:var(--font-display);font-size:var(--text-lg);margin:.2rem 0 .5rem}
.lane{display:inline-block;font-size:var(--text-xs);text-transform:uppercase;letter-spacing:.1em;color:var(--color-text-muted)}
.why{background:var(--callout-bg);padding:.6rem .8rem;font-size:var(--text-sm);margin-top:.5rem}
.sources,.src{font-size:var(--text-xs)}
.sources{margin-top:.5rem;color:var(--color-text-muted)}
.src{color:var(--color-accent);text-decoration:underline}
.quick-hits{list-style:none;display:grid;gap:.75rem}
.quick-hit{border-left:3px solid var(--gold);padding:.4rem .75rem}
.qh-text{font-size:var(--text-base)}
.data-grid,.voice-grid{display:grid;gap:1.25rem;grid-template-columns:1fr}
@media(min-width:720px){.data-grid,.voice-grid{grid-template-columns:1fr 1fr}}
.data-box,.voice-block{border:1px solid var(--color-divider);padding:1rem;background:var(--color-surface)}
.data-box h4,.voice-block h4{font-family:var(--font-display);font-size:var(--text-lg);margin-bottom:.5rem}
.data-table{width:100%;border-collapse:collapse;font-size:var(--text-sm)}
.data-table th,.data-table td{text-align:left;padding:.3rem .4rem;border-bottom:1px solid var(--color-divider);vertical-align:top}
.asof{color:var(--color-text-muted);font-size:var(--text-xs)}
.closer{font-family:var(--font-display);font-size:var(--text-lg);font-style:italic;
  border-left:4px solid var(--color-accent);padding:.5rem 1.25rem;color:var(--color-text)}
.closer footer{font-size:var(--text-sm);font-style:normal;color:var(--color-text-muted);margin-top:.5rem}
.receipt{border:2px solid var(--color-accent);padding:1.25rem;background:var(--color-surface)}
.receipt h4{font-family:var(--font-display);font-size:var(--text-lg);margin-bottom:.5rem}
.receipt p{font-size:var(--text-sm);margin-bottom:.5rem}
.receipt-link{margin-top:.5rem}
.receipt-link .src{font-weight:700}
.lp-hero{text-align:center;padding:3rem 1rem 2rem;border-bottom:3px double var(--color-divider)}
.lp-eyebrow{display:inline-block;font-size:var(--text-xs);font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);padding:.4rem .8rem;margin-bottom:1.5rem}
.lp-headline{font-family:var(--font-display);font-size:var(--text-2xl)}
.lp-subhead{font-family:var(--font-display);font-style:italic;color:var(--color-text-muted);max-width:52ch;margin:1rem auto}
.cta,.btn{display:inline-block;background:var(--accent);color:#fff;padding:.7rem 1.4rem;font-weight:700;border:none}
.cta:hover,.btn:hover{background:var(--accent-hover)}
.lp-structure{max-width:60ch;margin:1rem auto;display:grid;gap:.5rem}
.lp-form{display:flex;gap:.6rem;max-width:560px;margin:1rem auto;flex-wrap:wrap;justify-content:center}
.lp-form input[type=email],.lp-form input[type=text]:not(.lp-hp){flex:1 1 220px;padding:.7rem .9rem;border:1.5px solid var(--ink);background:var(--color-surface);color:var(--color-text)}
.lp-hp{position:absolute;left:-9999px;opacity:0;height:0;overflow:hidden}
.lp-form-note{font-size:var(--text-xs);color:var(--color-text-muted);text-align:center}
.prose{max-width:65ch;margin:0 auto}
.prose h1{font-family:var(--font-display);font-size:var(--text-xl);margin-bottom:1rem}
.prose h2{font-family:var(--font-display);margin:1.5rem 0 .5rem}
.prose p{margin-bottom:1rem}
.archive-list{list-style:none;display:grid;gap:.5rem;margin-top:1rem}
.archive-list a{color:var(--color-accent);text-decoration:underline}
/* v2 — centered closer */
.closer--centered{border-left:none;text-align:center;padding:1rem 1.25rem}
.closer--centered footer{text-align:center}
/* v2 — copy link button */
.copy-link-btn{display:inline-flex;align-items:center;gap:.3rem;font-size:var(--text-xs);
  color:var(--color-text-muted);background:none;border:1px solid var(--color-divider);
  padding:.2rem .5rem;cursor:pointer;font-family:var(--font-body);transition:all 180ms;
  text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.copy-link-btn:hover{color:var(--color-accent);border-color:var(--color-accent)}
/* v2 — briefing footer (sources left, copy link right) */
.briefing-foot{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin-top:.5rem;flex-wrap:wrap}
/* v2 — quick hit footer */
.qh-foot{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin-top:.3rem}
/* v2 — share runner bar */
.share-runner{display:flex;align-items:center;justify-content:center;gap:.75rem;
  padding:.75rem 1rem;border-top:2px solid var(--color-accent);border-bottom:2px solid var(--color-accent);
  margin-top:2rem;font-size:var(--text-sm);font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.share-runner-link{color:var(--color-accent);text-decoration:underline}
/* v2 — advertise page slots */
.ad-slots{display:grid;gap:1.25rem;margin:1.5rem 0}
.ad-slot{border:1px solid var(--color-divider);padding:1.25rem;background:var(--color-surface)}
.ad-slot h2{font-family:var(--font-display);font-size:var(--text-lg);margin-bottom:.5rem;color:var(--color-accent)}
/* v2 — sports quick hits */
.sports-hits{list-style:none;margin-bottom:.75rem;display:grid;gap:.4rem}
.sports-hit{font-size:var(--text-sm);border-left:3px solid var(--gold);padding:.3rem .6rem}
/* v2 — receipt claim/evidence styling */
.receipt-claim{font-weight:600;margin-bottom:.4rem}
.receipt-evidence{margin-bottom:.4rem}
"""


def build_site(editions: list[Edition], site_dir: Path | None = None) -> dict:
    """Render all pages. `editions` need not be every edition on disk — the
    generator scans site/editions for existing pages to keep the archive
    append-only. Returns a summary dict of written paths."""
    site_dir = Path(site_dir) if site_dir else config.SITE_DIR
    ed_dir = site_dir / "editions"
    ed_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "assets" / "css").mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    # Attach readable dates.
    for e in editions:
        if "date_readable" not in e.meta:
            try:
                e.meta["date_readable"] = datetime.strptime(e.date, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
            except ValueError:
                e.meta["date_readable"] = e.date

    # Edition pages.
    for e in editions:
        p = ed_dir / f"{e.date}.html"
        p.write_text(render_edition_page(e))
        written.append(str(p))

    # Discover the full archive from disk (append-only).
    existing_dates = sorted(
        {p.stem for p in ed_dir.glob("*.html")}, reverse=True
    )
    # Build lightweight Edition stubs for archive listing from what we have.
    known = {e.date: e for e in editions}
    archive_eds: list[Edition] = []
    for d in existing_dates:
        if d in known:
            archive_eds.append(known[d])
        else:
            stub = Edition(date=d)
            stub.meta["date_readable"] = d
            archive_eds.append(stub)

    latest = archive_eds[0] if archive_eds else None

    (site_dir / "assets" / "css" / "edition.css").write_text(EDITION_CSS)
    written.append(str(site_dir / "assets" / "css" / "edition.css"))

    pages = {
        "index.html": _landing_page(latest),
        "today.html": _today_page(latest),
        "archive.html": _archive_page(archive_eds),
        "corrections.html": _corrections_page(),
        "manifesto.html": _manifesto_page(),
        "subscribe.html": _subscribe_page(),
        "advertise.html": _advertise_page(),
        "404.html": T.page(f"{config.BRAND} — Not found",
                           '<section class="empty"><h1>404</h1><p>Page not found.</p>'
                           '<p><a href="index.html">Home</a></p></section>'),
    }
    for name, html_text in pages.items():
        p = site_dir / name
        p.write_text(html_text)
        written.append(str(p))

    return {"written": written, "editions": len(editions),
            "archive_total": len(archive_eds)}
