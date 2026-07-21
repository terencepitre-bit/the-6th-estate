from helpers import valid_edition
from sixth_estate.site.generator import build_site, render_edition_page


def test_render_edition_page_has_structure_and_sources():
    ed = valid_edition()
    html = render_edition_page(ed)
    for label in ("Briefings", "Quick Hits", "Data Boxes", "Voice Blocks", "The Closer"):
        assert label in html
    assert "DEMO EDITION" in html
    # A known source URL is present and rendered as a link.
    assert "MORTGAGE30US" in html
    assert 'rel="nofollow noopener"' in html


def test_build_site_writes_pages(tmp_path):
    ed = valid_edition("2026-07-20")
    summary = build_site([ed], site_dir=tmp_path)
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "today.html").exists()
    assert (tmp_path / "archive.html").exists()
    assert (tmp_path / "corrections.html").exists()
    assert (tmp_path / "manifesto.html").exists()
    assert (tmp_path / "subscribe.html").exists()
    assert (tmp_path / "editions" / "2026-07-20.html").exists()
    assert (tmp_path / "assets" / "css" / "edition.css").exists()
    assert summary["archive_total"] >= 1


def test_archive_is_append_only(tmp_path):
    build_site([valid_edition("2026-07-19")], site_dir=tmp_path)
    # A second build with a different date must keep the first edition page.
    build_site([valid_edition("2026-07-20")], site_dir=tmp_path)
    assert (tmp_path / "editions" / "2026-07-19.html").exists()
    assert (tmp_path / "editions" / "2026-07-20.html").exists()
    archive = (tmp_path / "archive.html").read_text()
    assert "2026-07-19" in archive and "2026-07-20" in archive


def test_html_escaping_prevents_injection(tmp_path):
    ed = valid_edition()
    ed.briefings[0].headline = "<script>alert(1)</script>"
    html = render_edition_page(ed)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- Asset/link path robustness (must resolve at root AND nested/proxied host) ---

# All local resource attributes are relative (never root-relative "/…"), so pages
# render styled under a private preview proxy, not just at the Netlify root.
_ROOT_RELATIVE_MARKERS = ('href="/', "href='/", 'src="/', "src='/", 'action="/', "action='/")


def _assert_no_root_relative(html: str):
    for marker in _ROOT_RELATIVE_MARKERS:
        assert marker not in html, f"root-relative path found: {marker}"


def test_top_level_pages_use_relative_assets(tmp_path):
    build_site([valid_edition("2026-07-20")], site_dir=tmp_path)
    for name in ("index.html", "today.html", "archive.html", "corrections.html",
                 "manifesto.html", "subscribe.html", "404.html"):
        html = (tmp_path / name).read_text()
        _assert_no_root_relative(html)
        assert 'href="assets/css/style.css"' in html
        assert 'href="assets/css/edition.css"' in html
        assert 'href="assets/favicon.svg"' in html
        # Nav resolves within the same directory.
        assert 'href="today.html"' in html
        assert 'href="index.html"' in html


def test_edition_pages_use_parent_relative_assets(tmp_path):
    build_site([valid_edition("2026-07-20")], site_dir=tmp_path)
    html = (tmp_path / "editions" / "2026-07-20.html").read_text()
    _assert_no_root_relative(html)
    # Depth-1 page must hop up one directory for every shared asset and nav link.
    assert 'href="../assets/css/style.css"' in html
    assert 'href="../assets/css/edition.css"' in html
    assert 'href="../assets/favicon.svg"' in html
    assert 'href="../today.html"' in html
    assert 'href="../index.html"' in html
    assert 'href="../archive.html"' in html


def test_archive_links_to_editions_relatively(tmp_path):
    build_site([valid_edition("2026-07-20")], site_dir=tmp_path)
    archive = (tmp_path / "archive.html").read_text()
    assert 'href="editions/2026-07-20.html"' in archive
    assert 'href="/editions/2026-07-20.html"' not in archive


def test_honeypot_hidden_without_css(tmp_path):
    build_site([valid_edition("2026-07-20")], site_dir=tmp_path)
    for name in ("index.html", "subscribe.html"):
        html = (tmp_path / name).read_text()
        # The honeypot input carries a CSS-independent inline hide + a11y opt-out,
        # so a missing stylesheet can never surface it to a human.
        assert 'name="website"' in html
        i = html.index('name="website"')
        field = html[html.rindex("<input", 0, i):html.index(">", i) + 1]
        assert "left:-9999px" in field
        assert 'aria-hidden="true"' in field
        assert 'tabindex="-1"' in field
        # Signup endpoint is reachable via a relative action.
        assert 'action="api/subscribe"' in html
