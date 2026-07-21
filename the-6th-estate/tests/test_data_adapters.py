"""Data adapters exercised with injected transports — zero network."""
from datetime import date

from sixth_estate.data import (fetch_cpi, fetch_crypto, fetch_forecast,
                               fetch_mortgage30us, fetch_on_this_day, fetch_scores)
from sixth_estate.data.sports import SportsDisabled


def test_fred_mortgage_with_transport():
    def transport(series_id):
        assert series_id == "MORTGAGE30US"
        return {"observations": [{"value": "6.55", "date": "2026-07-17"}]}
    m = fetch_mortgage30us(transport=transport)
    assert m.value == "6.55%"
    assert m.as_of == "2026-07-17"
    assert "MORTGAGE30US" in m.source.url


def test_bls_cpi_with_transport():
    def transport(series):
        return {"Results": {"series": [{"data": [
            {"value": "310.2", "periodName": "June", "year": "2026"}]}]}}
    m = fetch_cpi(transport=transport)
    assert m.value == "310.2"
    assert "June 2026" in m.as_of


def test_coingecko_with_transport():
    def transport(ids):
        return {"bitcoin": {"usd": 61250}, "ethereum": {"usd": 3180}}
    out = fetch_crypto(transport=transport)
    assert [m.label for m in out] == ["BTC", "ETH"]
    assert out[0].value == "$61,250"


def test_weather_with_transport():
    def transport(url):
        return {"properties": {"periods": [
            {"name": "Today", "temperature": 88, "temperatureUnit": "F",
             "shortForecast": "Sunny", "startTime": "2026-07-20T06:00:00-04:00"},
            {"name": "Tonight", "temperature": 70, "temperatureUnit": "F",
             "shortForecast": "Clear", "startTime": "2026-07-20T18:00:00-04:00"},
            {"name": "Tuesday", "temperature": 84, "temperatureUnit": "F",
             "shortForecast": "Storms", "startTime": "2026-07-21T06:00:00-04:00"},
        ]}}
    out = fetch_forecast(transport=transport, days=3)
    assert len(out) == 3
    assert "88" in out[0].value


def test_wikipedia_on_this_day_with_transport():
    def transport(mm, dd):
        return {"events": [{"year": 1969, "text": "A milestone.",
                            "pages": [{"content_urls": {"desktop": {
                                "page": "https://en.wikipedia.org/wiki/Apollo_11"}}}]}]}
    v = fetch_on_this_day(on=date(2026, 7, 20), transport=transport)
    assert v.kind == "this_day"
    assert "1969" in v.text
    assert v.source.url.endswith("Apollo_11")


def test_sports_disabled_without_provider():
    try:
        fetch_scores("mlb")
        assert False
    except SportsDisabled:
        pass


def test_sports_with_transport():
    def transport(league):
        return {"events": [{"name": "Home vs Away", "status": {"type": {
            "description": "Final"}}, "link": "https://www.mlb.com/gameday/1",
            "date": "2026-07-19T23:00Z"}]}
    out = fetch_scores("mlb", transport=transport)
    assert out[0].value == "Final"
