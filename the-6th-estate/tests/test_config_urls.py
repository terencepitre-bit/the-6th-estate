from sixth_estate import config


def test_bare_host_is_generic():
    assert config.is_generic_source_url("https://reuters.com/")
    assert config.is_generic_source_url("https://apnews.com")


def test_section_pages_are_generic():
    assert config.is_generic_source_url("https://www.reuters.com/world/us/")
    assert config.is_generic_source_url("https://apnews.com/politics")


def test_search_and_topic_pages_are_generic():
    assert config.is_generic_source_url("https://example.com/search?q=news")
    assert config.is_generic_source_url("https://example.com/topic/economy")
    assert config.is_generic_source_url("https://example.com/tag/politics")


def test_tracking_redirects_are_generic():
    assert config.is_generic_source_url("https://news.google.com/articles/xyz")
    assert config.is_generic_source_url("https://t.co/abc123")


def test_direct_article_is_not_generic():
    assert not config.is_generic_source_url(
        "https://www.federalregister.gov/documents/2026/07/18/2026-1/rule")
    assert not config.is_generic_source_url(
        "https://www.nejm.org/doi/full/10.1056/NEJMoa2400001")
    assert not config.is_generic_source_url("https://example.com/a-multi-word-slug-story")


def test_direct_source_urls_dedupes_and_filters():
    urls = ["https://example.com/",                       # generic -> dropped
            "https://example.com/real-story-here",
            "https://example.com/real-story-here/",        # dup
            {"url": "https://gov.example/doc-12345.pdf"}]
    out = config.direct_source_urls(urls)
    assert out == ["https://example.com/real-story-here",
                   "https://gov.example/doc-12345.pdf"]
