# THE 6th ESTATE — Master Manual

*The stories under the headlines.*
A Pitre Media publication. Editor: Terence Pitre, PhD.

This is the single authoritative reference for what THE 6th ESTATE publishes,
how it is produced, and the rules that govern quality, cost, and safety. It is
written for editors, maintainers, and contributors. Where this manual and the
code disagree, treat the disagreement as a bug and reconcile them.

> **A note on figures.** Every price, quota, rate limit, and model identifier in
> this manual is a **planning assumption**, not a guarantee. Providers change
> terms without notice. Before you rely on any cost or capability, verify the
> current provider documentation. Nothing here should be read as a promise of a
> specific API price or quota.

---

## 1. Mission and audience

THE 6th ESTATE is a daily editorial digest for a busy, intelligent general
reader who wants to understand the day — not just skim it. The promise is
**context over volume**: a small, fixed set of well-sourced items that explain
what happened and why it might matter, without hype, spin, or manufactured
urgency.

The audience is assumed to be capable and skeptical. They value:

- **Brevity with substance.** Every item earns its place; nothing is filler.
- **Traceability.** Every claim points to a specific, reachable source.
- **Neutral framing.** The reader draws conclusions; we supply grounded facts.

## 2. The editorial promise and differentiation

We differentiate on **discipline**, not scoops:

1. **A fixed shape.** The same 4 + 5 + 2 + 2 + 1 structure every day, so readers
   know exactly what they are getting and can read the whole thing in minutes.
2. **Exact-link sourcing.** We link the specific article, filing, or dataset —
   never a homepage, section index, search result, or tracking redirect.
3. **Free-access honesty.** We prefer freely reachable sources and never present
   a paywalled destination as free.
4. **Neutral voice.** We say "could" rather than "should," and we never invent
   scenes, people, or quotes.
5. **Visible corrections.** Errors are fixed in the open (see §12).

## 3. The canonical structure — 4 + 5 + 2 + 2 + 1 = 14

These counts are **locked**. Automatic publication requires all fourteen items,
each individually valid. (Manual preview may approve a reduced edition only if
every *displayed* item validates — see §14.)

1. **Briefings — 4**
2. **Quick Hits — 5**
3. **Data Boxes — 2** (Money Box; Scoreboard + Weather)
4. **Voice Blocks — 2** (This Day; The Number)
5. **The Closer — 1**

There is **no** Common Thread, **no** Receipts section, and **no** routine PDF.
Those were retired in the migration from the previous format (see `MIGRATION.md`).

## 4. Section definitions and story selection

### 4.1 Briefings (4 × 60–75 words)

Four briefings, each 60–75 words, one per lane:

1. **World / US lead** — the day's most consequential story.
2. **Money & Markets** — includes a **separate "Why it matters" line**.
3. **Business / Public Policy.**
4. **Science / Tech / Health, or Real Estate** — chosen by reader impact.

Sourcing:

- **Two independent direct sources** are required for the **lead** and the
  **Money & Markets** briefing.
- **One direct source** suffices for an ordinary briefing —
  **unless** the topic is high-risk (see §8), in which case two are required.

Selection favors stories with clear, checkable facts and durable relevance over
those that are merely trending. If a briefing cannot be sourced to the required
standard, it is dropped rather than weakened.

### 4.2 Quick Hits (5 × ≤25 words)

Five single-fact items, 25 words maximum each, each with **exactly one exact,
free-access source**. Quick Hits are factual and neutral — no analysis, no
editorializing, no adjectives doing argumentative work. They are the fast pulse
of the day between the longer briefings.

### 4.3 Data Boxes (2, zero writing cost)

Two boxes assembled entirely from data feeds — no prose to write, so no model
cost. **Every value displays its source and an as-of timestamp.**

- **Money Box:** S&P 500, Dow, Nasdaq, the 10-year Treasury yield, the 30-year
  fixed mortgage (FRED series `MORTGAGE30US`), BTC and ETH (CoinGecko), and CPI
  (BLS, series `CUUR0000SA0`).
- **Scoreboard + Weather:** MLB/NBA/NFL results from a permitted free feed, plus
  a three-day forecast from weather.gov.

### 4.4 Voice Blocks (2)

- **This Day:** a historical item from the Wikipedia "On This Day" feed, linked
  to its specific article.
- **The Number:** one sourced statistic that frames something in the day's news.

### 4.5 The Closer (1)

A short closing item — a quote, a curiosity, an "et cetera." When it states a
fact, it is sourced; when it is a quotation, it is attributed.

## 5. Source hierarchy and the exact-link policy

Preference order: **primary/official** (government agencies, filings, official
league/company releases) → **major wire/established outlets** → **reputable
specialist press**. Aggregators are a discovery aid only; we always resolve to
the underlying source.

**Exact links only.** A citation must point to the specific story, document, or
dataset page. The following are **rejected** automatically:

- bare homepages and section/landing pages;
- search-result, tag, topic, and category pages;
- tracking redirects (e.g. `news.google.com`, `l.facebook.com`, `t.co`,
  shorteners);
- malformed or unreachable URLs.

This rule is implemented once, in `config.is_generic_source_url` /
`direct_source_urls`, and imported by both the validators and the site
generator so the definition of "direct" cannot drift. Canonical dataset pages
(FRED series, CoinGecko coin pages, BLS release pages) are accepted by a
slightly looser data-box gate that still rejects bare hosts and search pages.

## 6. Free-access policy

We prefer sources a reader can open without a subscription. When the best
available source is paywalled, we **never label it free**; the `free_access`
flag on each source records this honestly, and the presentation reflects it. We
do not circumvent paywalls or link to pirated copies.

## 7. Word-count and tone rules

- Briefings: **60–75 words.** Quick Hits: **≤25 words.**
- Neutral, precise language. Prefer **"could"** to **"should"**; describe rather
  than prescribe.
- **No invented scenes, people, dialogue, or quotes.** Ever.
- No manufactured urgency, no loaded adjectives, no rhetorical questions
  standing in for reporting.

## 8. High-risk topics and the two-source rule

Certain topics carry outsized cost when wrong. For these, **two independent
direct sources are always required**, regardless of section:

> war/invasion/airstrike/ceasefire · elections/ballots/voters/recounts ·
> allegations/indictments/lawsuits/charges · abortion/immigration/deportation ·
> outbreaks/epidemics/pandemics/recalls · bankruptcy/default/collapse/layoffs/
> bailout.

Detection uses whole-word matching (so "war" does not trigger on "warned"). The
list lives in `config.HIGH_RISK_TERMS`; extend it as editorial judgment requires.

## 9. Data-box source definitions and timestamp policy

| Value            | Source                          | Notes |
|------------------|---------------------------------|-------|
| S&P/Dow/Nasdaq   | market data feed / FRED series  | index level + as-of |
| 10-yr Treasury   | FRED                            | yield + as-of |
| 30-yr mortgage   | FRED `MORTGAGE30US`             | weekly; show release date |
| BTC / ETH        | CoinGecko                       | USD spot + as-of |
| CPI              | BLS `CUUR0000SA0`               | show reference month/year |
| Scores           | permitted free league feed      | final/live status |
| Weather          | weather.gov (`api.weather.gov`) | 3-day forecast |

**Every displayed value carries an as-of timestamp** so readers can judge
staleness. A value with no verifiable timestamp is omitted rather than shown
undated.

## 10. Voice-block and closer rules

- **This Day** links the specific Wikipedia article for the event, not the day
  index.
- **The Number** cites the dataset or document the statistic comes from.
- **The Closer** is sourced when factual and attributed when quoted; a "fun"
  closer never invents a fact to be fun.

## 11. The low-cost technology stack and cost guardrails

Design goal: **run at or near \$0 on ordinary days**, spending only when a
section would otherwise be missing.

- **Discovery is RSS-first (\$0).** Feeds are configured via `SIXTHE_RSS_FEEDS`
  or documented public defaults. Confirm each feed is permitted for reuse.
- **Brave Search is a bounded fallback**, used only to fill missing sections and
  **capped per day** (`SIXTHE_BRAVE_DAILY_CAP`); disabled unless explicitly
  enabled with a key.
- **Google Programmable Search** is an optional backup, **disabled by default**.
- **SearXNG** is documented as a **future option only** — not implemented.
- **Models:** a Flash-Lite-class model for Quick Hits and a Flash-class model
  for Briefings. Model IDs are environment variables so a deprecated version can
  be swapped without code changes. The writer makes **one batched pass plus at
  most one fallback** (`SIXTHE_MODEL_CALL_LIMIT`, default 2), with **no repair
  loops**. Low temperature (0.2) for consistency.
- **Fail safe, don't fabricate.** On a bad or unparseable model response the
  writer returns nothing and the candidate is dropped.

All of these figures are planning assumptions — verify provider terms.

## 12. Correction policy

Corrections are public. When an error is found:

1. Fix the item and note the correction on the site's Corrections page.
2. Record what was wrong and when it was corrected.
3. Never silently rewrite history; the correction is part of the record.

The Corrections page is a standing page in the generated site.

## 13. Daily production workflow

1. **Curate** — discover candidates (RSS first, bounded fallback) and scaffold
   the edition. Without credentials this only scaffolds; it never fabricates.
2. **Draft** — the writer produces briefings/quick hits bound to their source
   URLs, within the call budget.
3. **Assemble** — data boxes and voice blocks are built from feeds; the edition
   is assembled with standard metadata (`structure = "4+5+2+2+1"`).
4. **Preview / validate** — run the validators; read the PASS/FAIL report.
5. **Human decision** — approve, skip, or place on edit-hold (see §14).
6. **Publish** — build the static site (idempotent). Email send is separately
   gated (see §15).

Each edition writes a JSON log line per step to `logs/<date>.log`. **Logs never
contain secrets** — the logger redacts credential-looking fields.

## 14. Human approval and publishing rules

- **Nothing publishes automatically by default.** `SIXTHE_AUTOMATION_ENABLED` is
  false and dry-run is the default posture.
- **Approve** is refused if the edition is invalid or falls below the
  publication floor (`SIXTHE_PUBLICATION_FLOOR`, default 14).
- **Skip** and **edit-hold** both block publishing until resolved.
- **Publication floor:** auto-publish requires all 14 validated items. A human
  may approve a **reduced** edition in preview **only if every displayed item
  individually validates** — we never show an item that fails its own rules.

## 15. Failure and hold rules

- A missing section is a failure, not something to paper over with invented
  content.
- If discovery cannot fill a section within budget, the section stays empty and
  the edition drops below the floor, which blocks auto-publish and routes to a
  human.
- **Edit-hold** (`edit --note "…"`) records why an edition is paused; **skip**
  records a decision not to publish that day. Both are auditable in state.

## 16. Website and email presentation

- **Website:** a static site generated into `./site` — landing page, Today,
  Archive, Corrections, Manifesto, and Subscribe pages, plus one page per
  edition. It reuses the established 6E visual language (paper/ink/accent
  palette, Instrument Serif + DM Sans). All user-facing content is
  HTML-escaped to prevent injection.
- **Email:** a responsive, inline-styled HTML email containing all five
  sections and (for demo editions) a clear DEMO banner and an unsubscribe token
  placeholder.

## 17. Archive and versioning

The archive is **append-only**: rebuilding the site never removes previously
published edition pages. `build-site` scans `site/editions/*.html`, preserves
existing pages, and regenerates the archive index across all of them. Edition
JSON in `editions/` is the source of truth; the HTML is a rendering of it.

## 18. Metrics

Track, at minimum: editions published, sections filled without paid fallback
(a proxy for cost discipline), fallback queries used vs. cap, model calls per
edition, validation failures by type, and email opens/clicks via Brevo (if
sending is enabled). Metrics collection must never log reader PII beyond what
the email provider already holds.

## 19. Security, privacy, and credential handling

- **No secrets in the repository.** All keys are read from the environment; see
  `.env.example`. `.env` is gitignored.
- **Secrets are never logged.** The logger drops fields whose names hint at
  credentials.
- **Least privilege:** enable only the providers you use; keep Brave/Google/
  email disabled unless needed.
- **Reader privacy:** subscription is consent-based; the signup function adds
  contacts with `updateEnabled` and never removes them from other lists.
- **Never present paywalled content as free**; never circumvent access controls.

## 20. GitHub and Netlify deployment

- **GitHub:** standard repo with `README`, `LICENSE` (MIT placeholder — confirm
  before public release), `.gitignore`, `.env.example`, and a **manual-only**
  CI workflow (`workflow_dispatch`, no schedule) that tests, compiles, validates
  the demo edition, and builds the site. No workflow publishes or sends.
- **Netlify:** `netlify.toml` publishes `./site` with an empty build command
  (pages are committed static assets) and bundles the signup Function with
  esbuild. `/api/subscribe` rewrites to the function. A locked-down CSP and
  security headers are set. Set `BREVO_API_KEY` in the Netlify UI, never in the
  repo.

## 21. Brevo configuration

- **List:** "The 6th Estate — Daily Readers" (default id 11; override with
  `BREVO_LIST_ID`).
- **Sender / reply-to:** `news@the6thestate.net` / `editor@the6thestate.net`
  (configurable). These are public brand identities, not secrets.
- **Auth:** the v3 API key travels in the `api-key` header, supplied at runtime
  from the environment — never committed, never logged.
- **Sending is triple-gated:** the `--send` flag **and** `SIXTHE_EMAIL_ENABLED=1`
  **and** a working transport/credential. Send is idempotent per edition.

## 22. Manual pilot and QA checklist

Before a real launch, walk this list:

- [ ] `python scripts/make_sample_edition.py` prints **PASS**.
- [ ] `python -m pytest tests/ -q` is green (offline).
- [ ] `python -m sixth_estate.cli build-site` produces the full site.
- [ ] Spot-check each demo source link resolves to a specific page.
- [ ] Confirm the DEMO banner appears on the demo edition (web + email).
- [ ] Confirm no real edition uses demo/fictional prose.
- [ ] Confirm `.env` is **not** committed and no key appears in `logs/`.
- [ ] Verify current provider terms/quotas/pricing for every enabled service.
- [ ] Responsive check: edition page and email at mobile and desktop widths.
- [ ] Confirm archive is preserved across two consecutive builds.

## 23. Future options (kept separate on purpose)

These are **not implemented** and are recorded so they are not mistaken for
current behavior:

- **SearXNG** self-hosted metasearch as an additional discovery fallback.
- Additional data boxes (e.g., commodities, FX) behind the same source/timestamp
  discipline.
- Scheduled automation — only after a sustained manual pilot and an explicit
  decision to flip `SIXTHE_AUTOMATION_ENABLED`.
- Personalization/segmentation of the email list.

Each would need its own cost review and a refresh of the guardrails in §11.
