from datetime import date, datetime, timezone
from urllib.error import HTTPError

from trading_agents.evaluation import reddit_coverage
from trading_agents.evaluation.reddit_coverage import (
    CandidateQuarter,
    CoverageScore,
    RedditPost,
    dedupe_posts,
    parse_reddit_atom,
    score_candidate_quarters,
)


ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/</id>
    <title>AAPL thread</title>
    <published>2026-02-03T12:34:56+00:00</published>
    <link href="https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/" />
    <content type="html">&lt;div&gt;&lt;!-- SC_OFF --&gt;&lt;p&gt;Body &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;&lt;!-- SC_ON --&gt;&lt;/div&gt;</content>
  </entry>
  <entry>
    <id>https://www.reddit.com/r/stocks/comments/abc/aapl_thread/</id>
    <title>Duplicate AAPL thread</title>
    <published>2026-02-04T12:34:56+00:00</published>
    <link href="https://www.reddit.com/r/stocks/comments/abc/aapl_thread/" />
    <content type="html">Duplicate body</content>
  </entry>
</feed>"""


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


def test_parse_reddit_atom_extracts_posts():
    posts = parse_reddit_atom(ATOM, ticker="AAPL", subreddit="wallstreetbets")

    assert posts == [
        RedditPost(
            ticker="AAPL",
            subreddit="wallstreetbets",
            title="AAPL thread",
            published_at=datetime(2026, 2, 3, 12, 34, 56, tzinfo=timezone.utc),
            published_date=date(2026, 2, 3),
            url="https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/",
            body="Body text",
        ),
        RedditPost(
            ticker="AAPL",
            subreddit="wallstreetbets",
            title="Duplicate AAPL thread",
            published_at=datetime(2026, 2, 4, 12, 34, 56, tzinfo=timezone.utc),
            published_date=date(2026, 2, 4),
            url="https://www.reddit.com/r/stocks/comments/abc/aapl_thread/",
            body="Duplicate body",
        ),
    ]


def test_main_prints_ranked_recommendation(monkeypatch, capsys):
    def fake_fetch_all_posts(*, tickers, subreddits, queries, request_delay_seconds):
        assert tickers == ("AAPL", "GOOGL", "AMZN")
        assert subreddits == ("wallstreetbets", "stocks", "investing")
        assert queries["AAPL"] == ("AAPL", "$AAPL", "Apple")
        assert request_delay_seconds == 3.0
        return [
            _post("AAPL", "wallstreetbets", "2026-01-02"),
            _post("GOOGL", "stocks", "2026-01-03"),
            _post("AMZN", "investing", "2026-01-04"),
            _post("AAPL", "wallstreetbets", "2025-10-02"),
        ]

    def fake_trading_days(start_date, end_date, benchmark):
        if start_date == date(2026, 1, 1):
            return [date(2026, 1, 5), date(2026, 1, 6)]
        return [start_date]

    monkeypatch.setattr(reddit_coverage, "fetch_all_posts", fake_fetch_all_posts)
    monkeypatch.setattr(reddit_coverage, "fetch_trading_days", fake_trading_days)

    reddit_coverage.main([])

    output = capsys.readouterr().out
    assert "Plan B Reddit coverage scan" in output
    assert "1. 2026-Q1" in output
    assert "Recommended Plan B period: 2026-Q1" in output


def test_dedupe_posts_prefers_first_url():
    posts = parse_reddit_atom(ATOM, ticker="AAPL", subreddit="wallstreetbets")

    assert dedupe_posts(posts) == [posts[0]]


def test_fetch_rss_posts_retries_429_before_success(monkeypatch):
    attempts = [
        HTTPError("https://reddit.example", 429, "Too Many Requests", None, None),
        HTTPError("https://reddit.example", 429, "Too Many Requests", None, None),
        FakeResponse(ATOM),
    ]
    sleeps = []

    def fake_urlopen(request, timeout):
        result = attempts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(reddit_coverage, "urlopen", fake_urlopen)
    monkeypatch.setattr(reddit_coverage.time, "sleep", sleeps.append)

    posts = reddit_coverage.fetch_rss_posts(
        ticker="AAPL",
        subreddit="wallstreetbets",
        query="AAPL",
    )

    assert len(posts) == 2
    assert sleeps == [10.0, 20.0]


def test_fetch_rss_posts_gives_up_after_three_429_retries(monkeypatch):
    attempts = [
        HTTPError("https://reddit.example", 429, "Too Many Requests", None, None)
        for _ in range(4)
    ]
    sleeps = []

    def fake_urlopen(request, timeout):
        raise attempts.pop(0)

    monkeypatch.setattr(reddit_coverage, "urlopen", fake_urlopen)
    monkeypatch.setattr(reddit_coverage.time, "sleep", sleeps.append)

    posts = reddit_coverage.fetch_rss_posts(
        ticker="AAPL",
        subreddit="wallstreetbets",
        query="AAPL",
    )

    assert posts == []
    assert sleeps == [10.0, 20.0, 40.0]


def _post(ticker: str, subreddit: str, yyyy_mm_dd: str) -> RedditPost:
    published_at = datetime.fromisoformat(yyyy_mm_dd + "T12:00:00+00:00")
    return RedditPost(
        ticker=ticker,
        subreddit=subreddit,
        title=f"{ticker} {yyyy_mm_dd}",
        published_at=published_at,
        published_date=published_at.date(),
        url=f"https://reddit.example/{ticker}/{subreddit}/{yyyy_mm_dd}",
        body="body",
    )


def test_score_candidate_quarters_uses_rolling_lookback_windows():
    candidates = [
        CandidateQuarter("2026-Q1", date(2026, 1, 1), date(2026, 1, 10)),
        CandidateQuarter("2026-Q2", date(2026, 4, 1), date(2026, 4, 10)),
    ]
    trading_days = {
        "2026-Q1": [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
        "2026-Q2": [date(2026, 4, 5), date(2026, 4, 6), date(2026, 4, 7)],
    }
    posts = [
        _post("AAPL", "wallstreetbets", "2026-01-02"),
        _post("GOOGL", "stocks", "2026-01-06"),
        _post("AMZN", "investing", "2026-01-07"),
        _post("AAPL", "wallstreetbets", "2026-04-01"),
        _post("AAPL", "stocks", "2026-04-04"),
        _post("GOOGL", "investing", "2026-04-02"),
        _post("AMZN", "stocks", "2026-04-03"),
        _post("AMZN", "investing", "2026-04-06"),
    ]

    scores = score_candidate_quarters(
        candidates,
        posts,
        tickers=("AAPL", "GOOGL", "AMZN"),
        subreddits=("wallstreetbets", "stocks", "investing"),
        trading_days_by_quarter=trading_days,
        lookback_days=7,
    )

    assert scores == [
        CoverageScore(
            quarter="2026-Q2",
            total_posts=5,
            ticker_day_count=9,
            covered_ticker_days_at_least_1=9,
            covered_ticker_days_at_least_3=0,
            min_ticker_coverage_at_least_1=1.0,
            nonzero_ticker_subreddit_pairs=5,
        ),
        CoverageScore(
            quarter="2026-Q1",
            total_posts=3,
            ticker_day_count=9,
            covered_ticker_days_at_least_1=6,
            covered_ticker_days_at_least_3=0,
            min_ticker_coverage_at_least_1=1 / 3,
            nonzero_ticker_subreddit_pairs=3,
        ),
    ]
