# Migration — from the 10-section format to 4 + 5 + 2 + 2 + 1

This repository replaces the previous edition of THE 6th ESTATE. The old system
lives alongside this one in the workspace and was **not deleted**; this document
records what changed and how continuity is preserved.

## What changed

### Format

| | Old format | New format |
|---|------------|------------|
| Shape | ~10 lettered sections (A1–A10: Front Page, The Ledger, The Signal, The World, The Vitals, The Circuit, The Classroom, The Arena, The Margin, Inspiration/Community) | **4 Briefings + 5 Quick Hits + 2 Data Boxes + 2 Voice Blocks + 1 Closer = 14 items** |
| Common Thread | present | **removed** |
| Receipts | present | **removed** |
| Routine PDF | generated daily | **removed** |
| Word limits | per-section, looser | Briefings 60–75 words; Quick Hits ≤25 words (enforced) |
| Sourcing | per-section guidance | one direct source per item; **two** for lead, Money & Markets, and all high-risk topics; exact-link policy enforced in code |
| Data | scattered | **two Data Boxes** with mandatory source + as-of timestamp on every value |

### Architecture

- **Stdlib-only runtime.** The new package (`sixth_estate/`) uses only the
  Python standard library at runtime; no third-party packages to install.
- **Injectable transports everywhere.** Every network adapter (discovery, data,
  writer, email) accepts an injected transport, so the entire test suite runs
  offline with zero network calls.
- **One source-URL rule.** `config.is_generic_source_url` / `direct_source_urls`
  is the single definition of a "direct" link, imported by both validators and
  the site generator so the two can never drift.
- **Explicit safety gates.** Automation is disabled by default; email is
  triple-gated; publishing requires approval and a publication floor.
- **Cost guardrails.** RSS-first discovery, a bounded/capped Brave fallback, a
  disabled Google PSE, a hard model-call ceiling, and safe-fail drafting.

### Website and email

- Reuses the existing 6E visual identity (paper/ink/accent palette, Instrument
  Serif + DM Sans) and the working Brevo signup Function.
- Standing pages preserved: landing, Archive, Corrections, Manifesto, Subscribe.
- The per-edition page and email are rebuilt for the 14-item structure.

## What is preserved

- **The brand and voice** — mission, tagline, editor byline, canonical domain.
- **The correction policy** — corrections remain public on a standing page.
- **The archive contract** — the archive is **append-only**; rebuilding never
  removes previously published edition pages.
- **The Netlify + Brevo conventions** — `/api/subscribe` rewrite, `api-key`
  header, list id 11, sender `news@the6thestate.net`. Security headers/CSP kept.

## Archive continuity

The new `build-site` scans `site/editions/*.html`, keeps every existing page,
and regenerates the archive index across all of them. To bring historical
editions into the new site, place their rendered `.html` files in
`site/editions/` (or re-render them from source data) and rebuild — old and new
editions will coexist in the archive. Old-format pages remain valid static HTML;
they simply predate the 14-item structure.

## Cutover checklist

- [ ] Confirm the demo edition validates (`python scripts/make_sample_edition.py`).
- [ ] Confirm the full offline suite passes (`python -m pytest tests/ -q`).
- [ ] Build the site and confirm both old and new edition pages appear in Archive.
- [ ] Point Netlify's publish directory at `site/` and set `BREVO_API_KEY` in the UI.
- [ ] Run a manual pilot before considering any automation.
- [ ] Retire the old pipeline only after the pilot succeeds.
