from io import StringIO

import pandas as pd
from urllib.error import URLError

from trading_agents.config.settings import (
    AppSettings,
    NewsSettings,
    SentimentSettings,
)
from trading_agents.tools import (
    fetch_reddit_posts,
    fetch_stocktwits_messages,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
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
    assert result == (
        "Stock data for AAPL from 2024-01-01 to 2024-01-03.\n"
        "Rows covered: 2.\n"
        "date,open,high,low,close,adj_close,volume\n"
        "2024-01-01,101,103,100,102,102,1100\n"
        "2024-01-02,102,104,101,103,103,1200"
    )


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
    calls = {}

    def fake_download(ticker, start, end, progress, auto_adjust):
        calls.update(
            ticker=ticker,
            start=start,
            end=end,
            progress=progress,
            auto_adjust=auto_adjust,
        )
        return _price_history(30)

    monkeypatch.setattr(
        market_data.yf,
        "download",
        fake_download,
    )

    result = get_indicators._run(
        "AAPL",
        "2024-01-01",
        "2024-02-01",
        "close_10_ema, rsi",
    )

    assert result == (
        "Technical indicators for AAPL from 2024-01-01 to 2024-02-01.\n"
        "Rows covered: 30.\n"
        "Requested indicators: close_10_ema, rsi.\n"
        "date,close,close_10_ema,rsi\n"
        "2024-01-01,102,102,50\n"
        "2024-01-02,103,102.55,100\n"
        "2024-01-03,104,103.1329,100\n"
        "2024-01-04,105,103.748,100\n"
        "2024-01-05,106,104.3945,100\n"
        "2024-01-06,107,105.0712,100\n"
        "2024-01-07,108,105.777,100\n"
        "2024-01-08,109,106.5102,100\n"
        "2024-01-09,110,107.2695,100\n"
        "2024-01-10,111,108.0531,100\n"
        "2024-01-11,112,108.8594,100\n"
        "2024-01-12,113,109.6867,100\n"
        "2024-01-13,114,110.5333,100\n"
        "2024-01-14,115,111.3974,100\n"
        "2024-01-15,116,112.2777,100\n"
        "2024-01-16,117,113.1723,100\n"
        "2024-01-17,118,114.0801,100\n"
        "2024-01-18,119,114.9994,100\n"
        "2024-01-19,120,115.9291,100\n"
        "2024-01-20,121,116.8681,100\n"
        "2024-01-21,122,117.8152,100\n"
        "2024-01-22,123,118.7694,100\n"
        "2024-01-23,124,119.7299,100\n"
        "2024-01-24,125,120.6959,100\n"
        "2024-01-25,126,121.6668,100\n"
        "2024-01-26,127,122.6417,100\n"
        "2024-01-27,128,123.6203,100\n"
        "2024-01-28,129,124.602,100\n"
        "2024-01-29,130,125.5864,100\n"
        "2024-01-30,131,126.5731,100"
    )
    assert calls == {
        "ticker": "AAPL",
        "start": "2019-01-01",
        "end": "2024-02-01",
        "progress": False,
        "auto_adjust": False,
    }


def test_indicators_use_warmup_history_then_trim_to_requested_window():
    dates = pd.bdate_range(end="2024-01-10", periods=240)
    values = pd.Series(range(1, len(dates) + 1), dtype=float).to_numpy()
    history = pd.DataFrame(
        {
            "Open": values + 100,
            "High": values + 102,
            "Low": values + 99,
            "Close": values + 101,
            "Volume": values * 100 + 1000,
        },
        index=dates,
    )

    result = market_data.render_indicators_text(
        "AAPL",
        "2024-01-02",
        "2024-01-06",
        ("boll", "boll_lb", "boll_ub", "close_200_sma"),
        history,
    )
    csv = pd.read_csv(StringIO(result.split("\n", 3)[3]))

    assert list(csv["date"]) == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    assert pd.notna(csv.iloc[0]["boll_lb"])
    assert pd.notna(csv.iloc[0]["boll_ub"])
    first_date = pd.Timestamp(csv.iloc[0]["date"])
    expected_sma = history.loc[:first_date, "Close"].tail(200).mean()
    assert csv.iloc[0]["close_200_sma"] == expected_sma


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

    assert result == (
        "Fundamentals for AAPL.\n"
        "Company: Apple Inc.\n"
        "Ticker: AAPL\n"
        "Sector: Technology\n"
        "Industry: Consumer Electronics\n"
        "Market capitalization: 3000000000000\n"
        "Trailing PE: 31.25\n"
        "Missing fields: Currency, Current price, Forward PE, Price to book, Enterprise value, "
        "Trailing EPS, Forward EPS, Dividend yield, Beta."
    )


def test_fundamentals_profile_uses_zero_trailing_dividend_yield(monkeypatch):
    class FakeTicker:
        info = {
            "longName": "Amazon.com, Inc.",
            "symbol": "AMZN",
            "trailingAnnualDividendYield": 0.0,
        }

    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda ticker: FakeTicker())

    result = get_fundamentals._run("amzn")

    assert "Dividend yield: 0" in result.splitlines()
    assert "Missing fields: Dividend yield" not in result


def test_dividend_yield_prefers_primary_and_normalises_trailing_ratio():
    assert (
        fundamentals._format_dividend_yield(
            {"dividendYield": 0.36, "trailingAnnualDividendYield": 0.0031}
        )
        == "0.36"
    )
    assert (
        fundamentals._format_dividend_yield(
            {"dividendYield": None, "trailingAnnualDividendYield": 0.0031}
        )
        == "0.31"
    )


def test_financial_statement_outputs(monkeypatch):
    class FakeTicker:
        balance_sheet = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [1000, 400],
                pd.Timestamp("2023-12-31"): [900, 350],
            },
            index=["Total Assets", "Total Liab"],
        )
        cashflow = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [250, 125],
                pd.Timestamp("2023-12-31"): [200, 100],
            },
            index=["Operating Cash Flow", "Capital Expenditure"],
        )
        income_stmt = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [500, 75],
                pd.Timestamp("2023-12-31"): [450, 70],
            },
            index=["Total Revenue", "Net Income"],
        )

    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda ticker: FakeTicker())

    assert get_balance_sheet._run("AAPL") == (
        "Balance sheet for AAPL.\n"
        "Rows covered: 2. Periods covered: 2.\n"
        "line_item,2024-12-31,2023-12-31\n"
        "Total Assets,1000,900\n"
        "Total Liab,400,350"
    )
    assert get_cashflow._run("AAPL") == (
        "Cash flow statement for AAPL.\n"
        "Rows covered: 2. Periods covered: 2.\n"
        "line_item,2024-12-31,2023-12-31\n"
        "Operating Cash Flow,250,200\n"
        "Capital Expenditure,125,100"
    )
    assert get_income_statement._run("AAPL") == (
        "Income statement for AAPL.\n"
        "Rows covered: 2. Periods covered: 2.\n"
        "line_item,2024-12-31,2023-12-31\n"
        "Total Revenue,500,450\n"
        "Net Income,75,70"
    )




def test_get_news_uses_upstream_default_limit(monkeypatch):
    class FakeTicker:
        news = [
            {
                "title": f"Headline {index}",
                "publisher": "Example News",
                "providerPublishTime": int(pd.Timestamp(f"2024-01-{index:02d} 12:00", tz="UTC").timestamp()),
                "link": f"https://example.com/{index}",
            }
            for index in range(1, 26)
        ]

    monkeypatch.setattr(news.yf, "Ticker", lambda query: FakeTicker())

    result = get_news._run("AAPL")

    assert result.count("### ") == 20
    assert "### Headline 25" in result
    assert "### Headline 6" in result
    assert "### Headline 5" not in result

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

    assert result == (
        "## AAPL News, from 2024-01-01 to 2024-01-03:\n\n"
        "### Apple unveils new chip (source: Example News)\n"
        "Apple unveiled a faster chip for upcoming devices.\n"
        "Link: https://example.com/aapl-chip\n"
    )


def test_global_news_limits_and_matches_upstream_style(monkeypatch):
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

    assert result == (
        "## Global Market News, from 2024-01-01 to 2024-01-03:\n\n"
        "### Index rally from ^GSPC (source: Market Desk)\n"
        "Link: https://example.com/^GSPC\n"
    )


def test_global_news_uses_configured_symbols(monkeypatch):
    published = int(pd.Timestamp("2024-01-02 15:00", tz="UTC").timestamp())
    seen_symbols = []

    class FakeTicker:
        def __init__(self, symbol):
            seen_symbols.append(symbol)
            self.news = [
                {
                    "title": f"Index rally from {symbol}",
                    "publisher": "Market Desk",
                    "providerPublishTime": published,
                    "link": f"https://example.com/{symbol}",
                }
            ]

    monkeypatch.setattr(
        news,
        "get_settings",
        lambda: AppSettings(news=NewsSettings(global_index_symbols=("SPY", "QQQ"))),
    )
    monkeypatch.setattr(news.yf, "Ticker", FakeTicker)

    result = news.get_global_news_text("2024-01-03")

    assert seen_symbols == ["SPY", "QQQ"]
    assert "### Index rally from SPY" in result
    assert "### Index rally from QQQ" in result


def test_sentiment_helpers_degrade_when_fetch_fails(monkeypatch):
    def fake_fetch(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)

    assert fetch_stocktwits_messages("AAPL") == "No data available for StockTwits messages for AAPL."


def test_reddit_degrades_when_rss_fetch_fails(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise URLError("network unavailable")

    monkeypatch.setattr(sentiment, "urlopen", fake_urlopen)

    assert fetch_reddit_posts("AAPL", inter_request_delay=0) == (
        "<no Reddit posts found mentioning AAPL across r/wallstreetbets, "
        "r/stocks, r/investing in the past 7 days>"
    )


def test_reddit_fetches_rss_first_and_omits_unavailable_metrics(monkeypatch):
    now = pd.Timestamp("2026-06-15 00:00:00", tz="UTC").timestamp()
    requested_urls = []
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Apple and the new AI-Siri: My thesis on AAPL</title>
    <published>2026-06-10T01:54:09+00:00</published>
    <content type="html">&lt;div&gt;&lt;!-- SC_OFF --&gt;&lt;p&gt;Line &lt;b&gt;one&lt;/b&gt;&lt;/p&gt;&lt;!-- SC_ON --&gt;&lt;/div&gt;</content>
  </entry>
</feed>"""

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return atom

    def fake_urlopen(request, timeout=10.0):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(sentiment, "urlopen", fake_urlopen)
    monkeypatch.setattr(sentiment.time, "time", lambda: now)

    result = fetch_reddit_posts(
        "AAPL",
        subreddits=("wallstreetbets",),
        limit_per_sub=5,
        inter_request_delay=0,
    )

    assert requested_urls == [
        "https://www.reddit.com/r/wallstreetbets/search.rss?q=AAPL&restrict_sr=on&sort=new&t=week&limit=5"
    ]
    assert result == (
        "r/wallstreetbets — 1 recent posts mentioning AAPL "
        "(via RSS feed; scores/comments unavailable):\n"
        " [2026-06-10] Apple and the new AI-Siri: My thesis on AAPL\n"
        " body excerpt: Line one"
    )


def test_reddit_json_helper_preserves_rich_metadata(monkeypatch):
    captured = {}

    def fake_fetch(url, headers=None, timeout=10.0):
        captured.update(url=url, headers=headers, timeout=timeout)
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "AAPL earnings thread",
                            "score": 42,
                            "num_comments": 17,
                            "created_utc": 1_718_000_000,
                            "selftext": "JSON body",
                        }
                    }
                ]
            }
        }

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)

    posts = sentiment._fetch_subreddit_json("AAPL", "wallstreetbets", 25, 1.5)

    assert captured == {
        "url": "https://www.reddit.com/r/wallstreetbets/search.json?q=AAPL&restrict_sr=on&sort=new&t=week&limit=25",
        "headers": {
            "User-Agent": "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)",
            "Accept": "application/json",
        },
        "timeout": 1.5,
    }
    assert posts == [
        {
            "title": "AAPL earnings thread",
            "score": 42,
            "num_comments": 17,
            "created_utc": 1_718_000_000,
            "selftext": "JSON body",
            "source": "json",
        }
    ]


def test_sentiment_helpers_match_upstream_success_formats(monkeypatch):
    now = 1_700_000_000
    trimmed_reddit_body = "Long analysis " + ("x" * 226) + "…"
    trimmed_stocktwits_body = ("x" * 280) + "…"

    def fake_fetch(url, headers=None, timeout=10.0):
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
        raise AssertionError("unexpected non-StockTwits fetch")

    def fake_fetch_posts(query, subreddit, limit, timeout):
        return [
            {
                "subreddit_name_prefixed": "r/stocks",
                "title": "AAPL earnings thread",
                "score": 8,
                "num_comments": 5,
                "created_utc": now - 60,
                "selftext": "Long\nanalysis " + "x" * 300,
            },
            {
                "subreddit_name_prefixed": "r/stocks",
                "title": "Low engagement AAPL thread",
                "score": 4,
                "num_comments": 5,
                "created_utc": now - 60,
                "selftext": "Still recent",
            },
            {
                "subreddit_name_prefixed": "r/stocks",
                "title": "Old AAPL thread",
                "score": 20,
                "num_comments": 15,
                "created_utc": now - sentiment.SECONDS_PER_WEEK - 1,
                "selftext": "Should also be filtered out",
            },
        ]

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)
    monkeypatch.setattr(sentiment, "_fetch_subreddit_posts", fake_fetch_posts)
    monkeypatch.setattr(sentiment.time, "time", lambda: now)

    stocktwits = fetch_stocktwits_messages("aapl")
    reddit = fetch_reddit_posts(
        "AAPL",
        subreddits=("stocks",),
        limit_per_sub=5,
        inter_request_delay=0,
    )

    assert stocktwits == (
        "Bullish: 1 (33%) · Bearish: 1 (33%) · Unlabeled: 1 · Total: 3 most-recent messages\n\n"
        "[2024-01-02T12:00:00Z · @market_user · Bullish] Bullish setup\n"
        "[2024-01-02T12:05:00Z · @macro_user · Bearish] Risk is rising\n"
        f"[2024-01-02T12:10:00Z · @long_user · no-label] {trimmed_stocktwits_body}"
    )
    assert reddit == (
        "r/stocks — 2 recent posts mentioning AAPL:\n"
        " [2023-11-14 ·    8↑ ·   5c] AAPL earnings thread\n"
        f" body excerpt: {trimmed_reddit_body}\n"
        " [2023-11-14 ·    4↑ ·   5c] Low engagement AAPL thread\n"
        " body excerpt: Still recent"
    )


def test_stocktwits_uses_settings_defaults_when_args_omitted(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        sentiment,
        "get_settings",
        lambda: AppSettings(
            sentiment=SentimentSettings(stocktwits_limit=12, stocktwits_timeout=1.5)
        ),
    )

    def fake_fetch(url, headers=None, timeout=10.0):
        captured.update(url=url, headers=headers, timeout=timeout)
        return {"messages": []}

    monkeypatch.setattr(sentiment, "_fetch_json", fake_fetch)

    fetch_stocktwits_messages("AAPL")

    assert captured["url"].endswith("/AAPL.json?limit=12")
    assert captured["timeout"] == 1.5


def test_reddit_uses_settings_defaults_for_fetch_and_recency(monkeypatch):
    now = 1_700_000_000
    calls = []

    monkeypatch.setattr(
        sentiment,
        "get_settings",
        lambda: AppSettings(
            sentiment=SentimentSettings(
                reddit_subreddits=("alpha", "beta"),
                reddit_limit_per_sub=2,
                reddit_timeout=1.25,
                reddit_inter_request_delay=0.0,
                reddit_recency_window_seconds=600,
            )
        ),
    )

    def fake_fetch_posts(query, subreddit, limit, timeout):
        calls.append((query, subreddit, limit, timeout))
        return [
            {
                "title": f"{subreddit} keep",
                "score": 11,
                "num_comments": 7,
                "created_utc": now - 60,
                "selftext": "kept",
            },
            {
                "title": f"{subreddit} low engagement",
                "score": 9,
                "num_comments": 7,
                "created_utc": now - 60,
                "selftext": "still recent",
            },
        ]

    monkeypatch.setattr(sentiment, "_fetch_subreddit_posts", fake_fetch_posts)
    monkeypatch.setattr(sentiment.time, "time", lambda: now)

    result = fetch_reddit_posts("AAPL")

    assert calls == [("AAPL", "alpha", 2, 1.25), ("AAPL", "beta", 2, 1.25)]
    assert "r/alpha — 2 recent posts mentioning AAPL:" in result
    assert "alpha low engagement" in result
    assert "r/beta — 2 recent posts mentioning AAPL:" in result


def test_reddit_names_an_empty_subreddit_in_a_mixed_result(monkeypatch):
    now = 1_700_000_000

    def fake_fetch_posts(query, subreddit, limit, timeout):
        if subreddit == "stocks":
            return [{"title": "recent", "created_utc": now - 60}]
        return []

    monkeypatch.setattr(sentiment, "_fetch_subreddit_posts", fake_fetch_posts)
    monkeypatch.setattr(sentiment.time, "time", lambda: now)

    result = fetch_reddit_posts(
        "googl",
        subreddits=("stocks", "investing"),
        inter_request_delay=0,
    )

    assert "r/stocks — 1 recent posts mentioning GOOGL:" in result
    assert result.endswith(
        "r/investing: <no posts found mentioning GOOGL in the past 7 days>"
    )
