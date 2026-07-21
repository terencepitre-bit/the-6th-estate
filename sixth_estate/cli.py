"""Command-line workflow for THE 6th ESTATE.

Automation is DISABLED by default. Nothing publishes or emails without explicit
flags AND the corresponding environment guards. Commands:

  curate   --date D            Discover + assemble a draft edition (writes editions/D.json).
  preview  --date D            Validate + render a preview page; print the report.
  approve  --date D            Record human approval (state -> approved).
  publish  --date D [--send]   Build the site from approved editions; optional gated email.
  skip     --date D            Mark an edition skipped (never publishes).
  edit     --date D --note ... Put an edition on edit-hold with a note.
  build-site                   Rebuild the static site from all editions on disk.

This module wires the pieces together; live discovery/model/data/email calls
happen only in `curate`/`publish` and only when credentials + flags are present.
Fixtures and tests never invoke the network paths.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .logging_util import EditionLogger
from .schema import Edition
from .site.generator import build_site
from .state import (APPROVED, CURATED, EDIT_HOLD, PREVIEWED, SKIPPED,
                    EditionState)
from .validation import validate_edition


def _load_edition(date: str) -> Edition | None:
    p = config.EDITIONS_DIR / f"{date}.json"
    if not p.exists():
        return None
    return Edition.load(p)


def _all_editions() -> list[Edition]:
    out = []
    for p in sorted(config.EDITIONS_DIR.glob("*.json")):
        try:
            out.append(Edition.load(p))
        except Exception:
            continue
    return out


def cmd_curate(args) -> int:
    """Assemble a draft edition. Runs the full live pipeline: RSS discovery,
    Gemini writing (if key present), data feeds, and assembly. Sections that
    don't need Gemini (data boxes, This Day, closer) always run."""
    date = args.date or config.today_et()
    log = EditionLogger(date)
    existing = _load_edition(date)
    if existing and not args.force:
        print(f"Edition {date} already exists (use --force to overwrite).")
        return 1

    from .pipeline import run_pipeline
    if not config.ANTHROPIC_API_KEY:
        print(f"WARNING: No ANTHROPIC_API_KEY — briefings/quick hits will be empty.")
        print(f"Data boxes, This Day, and closer will still run.")
    print(f"Running pipeline for {date}...")
    ed = run_pipeline(edition_date=date, log=log)
    total = (len(ed.briefings) + len(ed.quick_hits) + len(ed.data_boxes)
             + len(ed.voice_blocks) + (1 if ed.closer else 0)
             + (1 if ed.receipt else 0))
    print(f"Pipeline complete: {total} items.")

    ed.save(config.EDITIONS_DIR / f"{date}.json")
    st = EditionState.load_or_new(date)
    st.status = CURATED
    st.save()
    log.info("curated", date=date, items=total)
    return 0


def cmd_preview(args) -> int:
    date = args.date or config.today_et()
    ed = _load_edition(date)
    if not ed:
        print(f"No edition for {date}. Run `curate` first.")
        return 1
    result = validate_edition(ed, freshness_days=0 if ed.demo else args.freshness)
    print(f"Preview {date}: {result.summary()}")
    for f in result.findings:
        print(f"  [{f.level}] {f.item}: {f.message}")
    st = EditionState.load_or_new(date)
    st.status = PREVIEWED
    st.save()
    # Render a single edition page into the preview dir for visual QA.
    if args.render:
        from .site.generator import render_edition_page
        out = config.SITE_EDITIONS_DIR / f"{date}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_edition_page(ed))
        print(f"Rendered preview page: {out}")
    return 0 if result.ok else 2


def cmd_approve(args) -> int:
    date = args.date or config.today_et()
    ed = _load_edition(date)
    if not ed:
        print(f"No edition for {date}.")
        return 1
    result = validate_edition(ed, freshness_days=0 if ed.demo else args.freshness)
    floor = args.floor if args.floor is not None else config.PUBLICATION_FLOOR
    total = (len(ed.briefings) + len(ed.quick_hits) + len(ed.data_boxes)
             + len(ed.voice_blocks) + (1 if ed.closer else 0))
    if not result.ok:
        print(f"Refusing to approve: validation FAILED ({len(result.errors)} errors).")
        return 2
    if total < floor:
        print(f"Refusing to approve: {total} validated items < publication floor {floor}.")
        return 2
    st = EditionState.load_or_new(date)
    st.status = APPROVED
    st.save()
    print(f"Approved {date} ({total} items).")
    return 0


def cmd_skip(args) -> int:
    date = args.date or config.today_et()
    st = EditionState.load_or_new(date)
    st.status = SKIPPED
    st.notes.append(f"skipped:{datetime.now(timezone.utc).isoformat()}")
    st.save()
    print(f"Skipped {date}. It will not publish.")
    return 0


def cmd_edit(args) -> int:
    date = args.date or config.today_et()
    st = EditionState.load_or_new(date)
    st.status = EDIT_HOLD
    if args.note:
        st.notes.append(args.note)
    st.save()
    print(f"Edit-hold on {date}. Note recorded." if args.note else f"Edit-hold on {date}.")
    return 0


def cmd_publish(args) -> int:
    date = args.date or config.today_et()
    log = EditionLogger(date)
    ed = _load_edition(date)
    if not ed:
        print(f"No edition for {date}.")
        return 1
    st = EditionState.load_or_new(date)
    if st.status == SKIPPED:
        print(f"{date} is SKIPPED; not publishing.")
        return 1
    if st.status == EDIT_HOLD:
        print(f"{date} is on EDIT-HOLD; resolve edits and approve first.")
        return 1
    if st.status != APPROVED and not args.force:
        print(f"{date} is not APPROVED (status={st.status}). Approve first or use --force.")
        return 1

    result = validate_edition(ed, freshness_days=0 if ed.demo else args.freshness)
    if not result.ok and not args.force:
        print(f"Validation FAILED ({len(result.errors)} errors); not publishing.")
        return 2

    # Build/refresh the static site (idempotent, append-only archive).
    summary = build_site(_all_editions())
    when = datetime.now(timezone.utc).isoformat()
    first = st.mark_published(when)
    log.info("published", date=date, first_publish=first,
             pages=len(summary["written"]))
    print(f"{'Published' if first else 'Re-built (already published)'} {date}. "
          f"Site pages: {len(summary['written'])}.")

    # Email is a strictly-gated post-publish side effect.
    if args.send:
        from .email import send_edition
        try:
            res = send_edition(ed, st, send=True)
            print(f"Email: {res}")
            log.info("email", **{k: v for k, v in res.items() if k != "html"})
        except Exception as e:
            print(f"Email refused/failed: {e}")
            log.warning("email_refused", error=str(e)[:160])
    else:
        print("Email: skipped (no --send flag).")
    return 0


def cmd_build_site(args) -> int:
    summary = build_site(_all_editions())
    print(f"Built site: {len(summary['written'])} files, "
          f"{summary['archive_total']} archived editions.")
    return 0


def cmd_validate(args) -> int:
    """Validate a JSON edition file path directly (used by CI/tests)."""
    ed = Edition.load(Path(args.path))
    result = validate_edition(ed, freshness_days=0 if ed.demo else args.freshness)
    print(json.dumps({"ok": result.ok,
                      "errors": [f.__dict__ for f in result.errors],
                      "warnings": [f.__dict__ for f in result.warnings]}, indent=2))
    return 0 if result.ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sixth-estate",
                                description="THE 6th ESTATE daily edition workflow")
    p.add_argument("--freshness", type=int, default=3,
                   help="source freshness window in days (0 disables)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("curate"); c.add_argument("--date"); c.add_argument("--force", action="store_true"); c.set_defaults(func=cmd_curate)
    c = sub.add_parser("preview"); c.add_argument("--date"); c.add_argument("--render", action="store_true"); c.set_defaults(func=cmd_preview)
    c = sub.add_parser("approve"); c.add_argument("--date"); c.add_argument("--floor", type=int, default=None); c.set_defaults(func=cmd_approve)
    c = sub.add_parser("skip"); c.add_argument("--date"); c.set_defaults(func=cmd_skip)
    c = sub.add_parser("edit"); c.add_argument("--date"); c.add_argument("--note", default=""); c.set_defaults(func=cmd_edit)
    c = sub.add_parser("publish"); c.add_argument("--date"); c.add_argument("--send", action="store_true"); c.add_argument("--force", action="store_true"); c.set_defaults(func=cmd_publish)
    c = sub.add_parser("build-site"); c.set_defaults(func=cmd_build_site)
    c = sub.add_parser("validate"); c.add_argument("path"); c.set_defaults(func=cmd_validate)
    return p


def main(argv=None) -> int:
    config.ensure_dirs()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
