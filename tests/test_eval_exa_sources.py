"""Tests for Exa-backed evaluation source helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from trading_agents.evaluation import exa_sources


@dataclass
class FakeResult:
    title: str
    url: str
    published_date: str
    author: str | None = None
    summary: str | None = None
    text: str | None = None
    highlights: list[str] | None = None


class FakeSearchResponse:
    def __init__(self, results):
        self.results = results


class CapturingExa:
    calls = []
    results = []

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return FakeSearchResponse(self.results)


@pytest.fixture(autouse=True)
def fake_exa(monkeypatch):
    CapturingExa.calls = []
    CapturingExa.results = [
        FakeResult(
            title="Apple supplier shares rise",
            url="https://example.com/apple",
            published_date="2024-01-03T12:00:00Z",
            author="Example News",
            summary="Supplier optimism lifted the stock.",
        )
    ]
    monkeypatch.setattr(exa_sources, "Exa", CapturingExa)
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    return CapturingExa


def test_missing_exa_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="EXA_API_KEY is required"):
        exa_sources.fetch_news_via_exa("AAPL", "2024-01-01", "2024-01-03", 3)


def test_fetch_news_via_exa_uses_news_category_and_formats_block(fake_exa):
    result = exa_sources.fetch_news_via_exa("AAPL", "2024-01-01", "2024-01-03", 3)

    assert fake_exa.calls[0]["category"] == "news"
    assert fake_exa.calls[0]["start_published_date"] == "2024-01-01"
    assert fake_exa.calls[0]["end_published_date"] == "2024-01-03"
    assert fake_exa.calls[0]["num_results"] == 3
    assert "## AAPL News, from 2024-01-01 to 2024-01-03:" in result
    assert "### Apple supplier shares rise (source: Example News)" in result
    assert "Supplier optimism lifted the stock." in result
    assert "Link: https://example.com/apple" in result


def test_fetch_global_news_via_exa_computes_lookback_window(fake_exa):
    result = exa_sources.fetch_global_news_via_exa("2024-01-10", 7, 5)

    assert fake_exa.calls[0]["category"] == "news"
    assert fake_exa.calls[0]["start_published_date"] == "2024-01-03"
    assert fake_exa.calls[0]["end_published_date"] == "2024-01-10"
    assert fake_exa.calls[0]["num_results"] == 5
    assert "## Global Market News, from 2024-01-03 to 2024-01-10:" in result


def test_exa_timeout_patch_overrides_explicit_none(monkeypatch):
    observed = {}

    def fake_post(*args, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        return object()

    monkeypatch.setattr(exa_sources.exa_api.requests, "post", fake_post)

    with exa_sources._exa_request_timeout_patch():
        exa_sources.exa_api.requests.post("https://example.com", timeout=None)

    assert observed["timeout"] == exa_sources.EXA_REQUEST_TIMEOUT_SECONDS


def test_fetch_reddit_via_exa_uses_reddit_domain_and_formats_posts(fake_exa):
    fake_exa.results = [
        FakeResult(
            title="AAPL discussion",
            url="https://www.reddit.com/r/stocks/comments/abc",
            published_date="2024-01-04",
            text="Investors discuss Apple demand.",
        )
    ]

    result = exa_sources.fetch_reddit_via_exa("aapl", "2024-01-01", "2024-01-05", 2)

    assert fake_exa.calls[0]["include_domains"] == ["reddit.com"]
    assert fake_exa.calls[0]["start_published_date"] == "2024-01-01"
    assert fake_exa.calls[0]["end_published_date"] == "2024-01-05"
    assert "Reddit posts mentioning AAPL from 2024-01-01 to 2024-01-05:" in result
    assert "[2024-01-04] AAPL discussion" in result
    assert "body excerpt: Investors discuss Apple demand." in result


def test_fetch_stocktwits_via_exa_uses_stocktwits_domain(fake_exa):
    fake_exa.results = [
        FakeResult(
            title="$AAPL setup",
            url="https://stocktwits.com/example/message/1",
            published_date="2024-01-04",
            summary="Watching the chart.",
        )
    ]

    result = exa_sources.fetch_stocktwits_via_exa("aapl", "2024-01-01", "2024-01-05", 2)

    assert fake_exa.calls[0]["include_domains"] == ["stocktwits.com"]
    assert "Total: 1 historical StockTwits results for AAPL" in result
    assert "[2024-01-04 | no-label] $AAPL setup - Watching the chart." in result


def test_social_helpers_return_existing_fallback_strings(fake_exa):
    fake_exa.results = []

    assert (
        exa_sources.fetch_reddit_via_exa("AAPL", "2024-01-01", "2024-01-05", 2)
        == "No data available for Reddit posts for AAPL."
    )
    assert (
        exa_sources.fetch_stocktwits_via_exa("AAPL", "2024-01-01", "2024-01-05", 2)
        == "No data available for StockTwits messages for AAPL."
    )
