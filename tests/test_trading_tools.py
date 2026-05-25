import pandas as pd

from trading_agents.tools import (
    fetch_reddit_posts,
    fetch_stocktwits_messages,
    get_balance_sheet,
    get_fundamentals,
    get_global_news,
    get_indicators,
    get_news,
    get_stock_data,
)
from trading_agents.tools import fundamentals, market_data, news, sentiment


def _price_history(rows: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    values = range(1, rows + 1)
    return pd.DataFrame(
        {
            "Open": [100 + value for value in values],
            "High": [102 + value for value in values],
            "Low": [99 + value for value in values],
            "Close": [101 + value for value in values],
            "Adj Close": [101 + value for value in values],
            "Volume": [1000 + value * 100 for value in values],
        },
        index=dates,
    )


def test_stock_data_formats_history(monkeypatch):
    calls = {}

    def fake_download(ticker, start, end, progress, auto_adjust):
        calls.update(
            ticker=ticker,
            start=start,
            end=end,
            progress=progress,
            auto_adjust=auto_adjust,
        )
        return _price_history(2)

    monkeypatch.setattr(market_data.yf, "download", fake_download)

    result = get_stock_data._run("aapl", "2024-01-01", "2024-01-03")

    assert calls == {
        "ticker": "AAPL",
        "start": "2024-01-01",
        "end": "2024-01-03",
        "progress": False,
        "auto_adjust": False,
    }
    assert "Stock data for AAPL from 2024-01-01 to 2024-01-03." in result
    assert "Rows covered: 2." in result
    assert "date,open,high,low,close,adj_close,volume" in result
    assert "2024-01-02,102,104,101,103,103,1200" in result


def test_stock_data_empty_response(monkeypatch):
    monkeypatch.setattr(market_data.yf, "download", lambda *args, **kwargs: pd.DataFrame())

    result = get_stock_data._run("MSFT", "2024-01-01", "2024-01-03")

    assert result == "No price data available for MSFT between 2024-01-01 and 2024-01-03."


def test_indicators_reject_invalid_name_without_download(monkeypatch):
    def fake_download(*args, **kwargs):
        raise AssertionError("download should not run for invalid indicators")

    monkeypatch.setattr(market_data.yf, "download", fake_download)

    result = get_indicators._run("AAPL", "2024-01-01", "2024-01-05", ["rsi", "unknown"])

    assert "Validation error: unsupported indicators: unknown." in result
    assert "close_50_sma" in result


def test_indicators_format_requested_values(monkeypatch):
    monkeypatch.setattr(
        market_data.yf,
        "download",
        lambda *args, **kwargs: _price_history(30),
    )

    result = get_indicators._run(
        "AAPL",
        "2024-01-01",
        "2024-02-01",
        "close_10_ema, rsi",
    )

    assert "Technical indicators for AAPL from 2024-01-01 to 2024-02-01." in result
    assert "Requested indicators: close_10_ema, rsi." in result
    assert "date,close,close_10_ema,rsi" in result
    assert "2024-01-30" in result


def test_fundamentals_profile_reports_missing_fields(monkeypatch):
    class FakeTicker:
        info = {
            "longName": "Apple Inc.",
            "symbol": "AAPL",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3000000000000,
            "trailingPE": 31.25,
        }

    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda ticker: FakeTicker())

    result = get_fundamentals._run("aapl")

    assert "Fundamentals for AAPL." in result
    assert "Company: Apple Inc." in result
    assert "Sector: Technology" in result
    assert "Market capitalization: 3000000000000" in result
    assert "Missing fields:" in result
    assert "Forward PE" in result


def test_statement_formatting(monkeypatch):
    class FakeTicker:
        balance_sheet = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [1000, 400],
                pd.Timestamp("2023-12-31"): [900, 350],
            },
            index=["Total Assets", "Total Liab"],
        )
        cashflow = pd.DataFrame()
        income_stmt = pd.DataFrame()

    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda ticker: FakeTicker())

    result = get_balance_sheet._run("AAPL")

    assert "Balance sheet for AAPL." in result
    assert "Rows covered: 2. Periods covered: 2." in result
    assert "line_item,2024-12-31,2023-12-31" in result
    assert "Total Assets,1000,900" in result


def test_news_formats_and_filters(monkeypatch):
    included_time = int(pd.Timestamp("2024-01-02 12:00", tz="UTC").timestamp())
    excluded_time = int(pd.Timestamp("2023-12-15 12:00", tz="UTC").timestamp())

    class FakeTicker:
        news = [
            {
                "title": "Apple unveils new chip",
                "publisher": "Example News",
                "providerPublishTime": included_time,
                "summary": "Apple unveiled a faster chip for upcoming devices.",
                "link": "https://example.com/aapl-chip",
            },
            {
                "title": "Old headline",
                "publisher": "Example News",
                "providerPublishTime": excluded_time,
                "link": "https://example.com/old",
            },
        ]

    monkeypatch.setattr(news.yf, "Ticker", lambda query: FakeTicker())

    result = get_news._run("AAPL", "2024-01-01", "2024-01-03", limit=5)

    assert "News for AAPL between 2024-01-01 and 2024-01-03." in result
    assert "Apple unveils new chip" in result
    assert "Example News" in result
    assert "Published: 2024-01-02 12:00" in result
    assert "Apple unveiled a faster chip for upcoming devices." in result
    assert "https://example.com/aapl-chip" in result
    assert "Old headline" not in result


def test_global_news_limits_and_declares_yahoo_limitation(monkeypatch):
    published = int(pd.Timestamp("2024-01-02 15:00", tz="UTC").timestamp())

    class FakeTicker:
        def __init__(self, symbol):
            self.news = [
                {
                    "title": f"Index rally from {symbol}",
                    "publisher": "Market Desk",
                    "providerPublishTime": published,
                    "link": f"https://example.com/{symbol}",
                }
            ]

    monkeypatch.setattr(news.yf, "Ticker", FakeTicker)

    result = get_global_news._run("2024-01-03", look_back_days=2, limit=1)

    assert result.startswith("Source limitation: global news currently uses Yahoo Finance")
    assert "Global market news from 2024-01-01 to 2024-01-03." in result
    assert result.count("Index rally") == 1


def test_sentiment_helpers_degrade_when_fetch_fails(monkeypatch):
    def fake_fetch(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)

    assert fetch_stocktwits_messages("AAPL") == "No data available for StockTwits messages for AAPL."
    reddit = fetch_reddit_posts("AAPL")
    assert "No data available for Reddit posts for AAPL." in reddit
    assert "r/wallstreetbets, r/stocks, r/investing" in reddit


def test_sentiment_helpers_format_fixture_payloads(monkeypatch):
    now = 1_700_000_000

    def fake_fetch(url, headers=None):
        if "stocktwits" in url:
            return {
                "messages": [
                    {
                        "created_at": "2024-01-02T12:00:00Z",
                        "body": "Bullish\nsetup",
                        "user": {"username": "market_user"},
                        "entities": {"sentiment": {"basic": "Bullish"}},
                    },
                    {
                        "created_at": "2024-01-02T12:05:00Z",
                        "body": "Risk is rising",
                        "user": {"username": "macro_user"},
                        "entities": {"sentiment": {"basic": "Bearish"}},
                    },
                    {
                        "created_at": "2024-01-02T12:10:00Z",
                        "body": "x" * 400,
                        "user": {"username": "long_user"},
                    },
                ]
            }
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "subreddit_name_prefixed": "r/stocks",
                            "title": "AAPL earnings thread",
                            "score": 8,
                            "num_comments": 5,
                            "created_utc": now - 60,
                            "selftext": "Long\nanalysis " + "x" * 300,
                            "permalink": "/r/stocks/comments/abc/aapl/",
                        }
                    },
                    {
                        "data": {
                            "subreddit_name_prefixed": "r/stocks",
                            "title": "Low quality AAPL thread",
                            "score": 4,
                            "num_comments": 5,
                            "created_utc": now - 60,
                            "selftext": "Should be filtered out",
                        }
                    },
                    {
                        "data": {
                            "subreddit_name_prefixed": "r/stocks",
                            "title": "Old AAPL thread",
                            "score": 20,
                            "num_comments": 15,
                            "created_utc": now - sentiment.SECONDS_PER_WEEK - 1,
                            "selftext": "Should also be filtered out",
                        }
                    },
                ]
            }
        }

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)
    monkeypatch.setattr(sentiment.time, "time", lambda: now)

    stocktwits = fetch_stocktwits_messages("aapl")
    reddit = fetch_reddit_posts("AAPL", subreddits=("stocks",), limit_per_sub=5)

    assert stocktwits.startswith(
        "Bullish: 1 (33%) - Bearish: 1 (33%) - Unlabeled: 1 - Total: 3 most-recent messages"
    )
    assert "[2024-01-02T12:00:00Z - @market_user - Bullish] Bullish setup" in stocktwits
    assert "[2024-01-02T12:05:00Z - @macro_user - Bearish] Risk is rising" in stocktwits
    assert "@long_user - no-label" in stocktwits
    assert "x" * 281 not in stocktwits

    assert "r/stocks - 1 high-quality recent posts mentioning AAPL:" in reddit
    assert "[2023-11-14 -    8 upvotes -   5 comments] AAPL earnings thread" in reddit
    assert "body excerpt: Long analysis" in reddit
    assert "x" * 241 not in reddit
    assert "Low quality AAPL thread" not in reddit
    assert "Old AAPL thread" not in reddit
