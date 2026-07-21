# THE 6th ESTATE

*The stories under the headlines.* — A Pitre Media publication.

A low-cost, human-in-the-loop daily newsletter system: it discovers sourced
stories, drafts a fixed-format edition, validates every item against strict
editorial rules, and renders a static website and an email — with publishing and
sending **disabled by default**.

> **Status:** GitHub-ready. Runs fully **offline** in demo/dry-run mode with no
> credentials. Nothing publishes, emails, or calls a paid API unless an operator
> explicitly opts in with both a flag and an environment variable.

---

## The edition format — 4 + 5 + 2 + 2 + 1 = 14 items

Every edition is exactly fourteen items, in this order:

| # | Section       | Count | Rule of thumb |
|---|---------------|-------|---------------|
| 1 | **Briefings** | 4     | 60–75 words each; lanes: World/US lead, Money & Markets (+ "Why it matters"), Business/Public Policy, Science/Tech/Health or Real Estate. Lead + Money briefings need two sources; high-risk topics always need two. |
| 2 | **Quick Hits**| 5     | ≤25 words, one exact free-access source each, factual and neutral. |
| 3 | **Data Boxes**| 2     | Money Box (equities, 10-yr Treasury, 30-yr mortgage, BTC/ETH, CPI) and Scoreboard + 3-day weather. Every value shows source + as-of timestamp. Zero writing cost. |
| 4 | **Voice Blocks**| 2   | This Day (Wikipedia On This Day) and The Number (one sourced statistic). |
| 5 | **The Closer**| 1     | A quote/curiosity, sourced when factual. |

The full editorial contract — story selection, source hierarchy, exact-link
policy, free-access policy, tone, high-risk two-source rules, correction policy,
cost guardrails, and the daily workflow — lives in
[`docs/THE_6TH_ESTATE_MASTER_MANUAL.md`](docs/THE_6TH_ESTATE_MASTER_MANUAL.md).

---

## Quick start (offline, no keys)

Requires **Python 3.11+**. No third-party runtime dependencies.

```bash
# 1) Generate and validate the labeled DEMO edition
python scripts/make_sample_edition.py

# 2) Build the static site into ./site
python -m sixth_estate.cli build-site

# 3) Run the offline test suite (no network)
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Open `site/index.html` in a browser to preview.

---

## The daily workflow (CLI)

```
python -m sixth_estate.cli <command>
```

| Command      | What it does |
|--------------|--------------|
| `curate`     | Discover candidates and scaffold an edition. Without credentials it only scaffolds — it never fabricates content. |
| `preview`    | Validate an edition and print a PASS/FAIL report. `--render` also writes its page. |
| `approve`    | Mark an edition APPROVED. Refuses if it is invalid or below the publication floor. |
| `skip`       | Mark an edition SKIPPED (blocks publish). |
| `edit`       | Put an edition on EDIT_HOLD with `--note "reason"` (blocks publish). |
| `publish`    | Build the site for an approved edition (idempotent). Email send is separately gated behind `--send`. |
| `build-site` | Regenerate the whole static site from committed editions. |
| `validate`   | Validate an edition JSON file by path. |

Publishing is refused unless an edition is APPROVED (or `--force`) and at or
above `SIXTHE_PUBLICATION_FLOOR` (default: all 14 items).

---

## Safety posture

- **Automation off by default.** `SIXTHE_AUTOMATION_ENABLED=false`; dry-run is the default.
- **Email is triple-gated:** the `--send` flag **and** `SIXTHE_EMAIL_ENABLED=1` **and** a working transport/credential. Missing any one raises rather than sends.
- **No secrets in the repo.** All keys come from the environment (see `.env.example`). Secrets are never logged; the logger redacts credential-looking fields.
- **Tests never touch the network.** Every adapter takes an injectable transport; the suite runs fully offline.
- **Demo data is labeled.** The sample edition is marked `demo` and shows a "DEMO EDITION" banner — it is not real current news.

---

## Configuration

Copy `.env.example` to `.env` and fill in only what you need. With nothing set,
the system runs offline in demo mode. Key groups: discovery (RSS + optional
Brave/Google fallbacks), data APIs (FRED, BLS, CoinGecko, weather.gov,
Wikipedia, optional sports), Gemini model IDs, and Brevo email.

> All quotas, prices, and model IDs in `.env.example` and the manual are
> **planning assumptions**. Verify current provider terms before relying on them.

---

## Deployment (Netlify)

`netlify.toml` publishes `./site` and bundles the signup Function at
`site/netlify/functions/subscribe.js`, which adds consenting contacts to the
Brevo "Daily Readers" list. Set `BREVO_API_KEY` (and optionally `BREVO_LIST_ID`)
in the Netlify UI — never in the repo. Security headers and a locked-down CSP
are configured in `netlify.toml`.

---

## Repository layout

```
sixth_estate/        # runtime package (stdlib-only)
  config.py          # env-driven config; direct-source URL rules
  schema.py          # 14-item edition dataclasses
  validation/        # editorial validators
  discovery/         # RSS-first + bounded Brave / disabled Google PSE
  data/              # FRED, BLS, CoinGecko, weather.gov, Wikipedia, sports
  writer/            # Gemini writer (configurable, bounded, safe-fail)
  build/             # data boxes, voice blocks, edition assembly
  site/              # static site generator + templates
  email/             # Brevo HTML builder + gated send
  state.py           # idempotent per-edition state
  cli.py             # curate/preview/approve/skip/edit/publish/build-site
scripts/             # make_sample_edition.py and helpers
tests/               # offline pytest suite (55 tests)
site/                # generated static site + Netlify function/assets
docs/                # master manual
editions/ state/ logs/ fixtures/   # working data (state/logs are gitignored)
```

## Migration

This repository replaces the previous 10-section format. See
[`MIGRATION.md`](MIGRATION.md) for what changed and how archives are preserved.

## License

Released under the **MIT License** (see [`LICENSE`](LICENSE)). MIT is a
permissive placeholder chosen for portability; substitute your preferred license
before public release if MIT is not intended.
