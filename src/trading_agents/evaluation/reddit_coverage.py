from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping
import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from trading_agents.config import get_settings
from trading_agents.tools.sentiment import REDDIT_HEADERS


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
REDDIT_HTTP_429_RETRY_DELAYS = (10.0, 20.0, 40.0)


@dataclass(frozen=True)
class RedditPost:
    ticker: str
    subreddit: str
    title: str
    published_at: datetime
    published_date: date
    url: str
    body: str


@dataclass(frozen=True)
class CandidateQuarter:
    name: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class CoverageScore:
    quarter: str
    total_posts: int
    ticker_day_count: int
    covered_ticker_days_at_least_1: int
    covered_ticker_days_at_least_3: int
    min_ticker_coverage_at_least_1: float
    nonzero_ticker_subreddit_pairs: int


DEFAULT_CANDIDATES = (
    CandidateQuarter("2025-Q3", date(2025, 7, 1), date(2025, 9, 30)),
    CandidateQuarter("2025-Q4", date(2025, 10, 1), date(2025, 12, 31)),
    CandidateQuarter("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
)
DEFAULT_QUERY_ALIASES = {
    "AAPL": ("AAPL", "$AAPL", "Apple"),
    "GOOGL": ("GOOGL", "$GOOGL", "Google"),
    "AMZN": ("AMZN", "$AMZN", "Amazon"),
}


def parse_reddit_atom(payload: bytes, *, ticker: str, subreddit: str) -> list[RedditPost]:
    root = ET.fromstring(payload)
    posts: list[RedditPost] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        published_el = entry.find("atom:published", ATOM_NS)
        link_el = entry.find("atom:link", ATOM_NS)
        content_el = entry.find("atom:content", ATOM_NS)
        published_at = _parse_atom_datetime(
            published_el.text if published_el is not None else None
        )
        if published_at is None:
            continue
        posts.append(
            RedditPost(
                ticker=ticker.upper().strip(),
                subreddit=subreddit,
                title=_one_line(title_el.text if title_el is not None else ""),
                published_at=published_at,
                published_date=published_at.date(),
                url=link_el.attrib.get("href", "") if link_el is not None else "",
                body=_strip_reddit_html(
                    content_el.text if content_el is not None and content_el.text else ""
                ),
            )
        )
    return posts


def dedupe_posts(posts: list[RedditPost]) -> list[RedditPost]:
    seen: set[str] = set()
    deduped: list[RedditPost] = []
    for post in posts:
        key = _dedupe_key(post)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)
    return deduped


def score_candidate_quarters(
    candidates: Iterable[CandidateQuarter],
    posts: list[RedditPost],
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    trading_days_by_quarter: Mapping[str, list[date]],
    lookback_days: int,
) -> list[CoverageScore]:
    deduped = dedupe_posts(posts)
    scores = [
        _score_one_candidate(
            candidate,
            deduped,
            tickers=tickers,
            subreddits=subreddits,
            trading_days=trading_days_by_quarter[candidate.name],
            lookback_days=lookback_days,
        )
        for candidate in candidates
    ]
    return sorted(
        scores,
        key=lambda score: (
            score.covered_ticker_days_at_least_1 / max(score.ticker_day_count, 1),
            score.covered_ticker_days_at_least_3 / max(score.ticker_day_count, 1),
            score.min_ticker_coverage_at_least_1,
            score.total_posts,
        ),
        reverse=True,
    )


def fetch_all_posts(
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    queries: Mapping[str, tuple[str, ...]],
    request_delay_seconds: float,
) -> list[RedditPost]:
    posts: list[RedditPost] = []
    first = True
    for ticker in tickers:
        for subreddit in subreddits:
            # OR the alias tuple into a single query so each (ticker, subreddit)
            # pair costs one request instead of one per alias. This keeps Reddit
            # RSS volume to len(tickers) * len(subreddits) requests and avoids the
            # unauthenticated rate limit that returns HTTP 429.
            query = _join_query_aliases(queries.get(ticker, (ticker,)))
            if not first and request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            first = False
            posts.extend(fetch_rss_posts(ticker=ticker, subreddit=subreddit, query=query))
    return dedupe_posts(posts)


def _join_query_aliases(aliases: tuple[str, ...]) -> str:
    return " OR ".join(alias for alias in aliases if alias) or ""


def fetch_rss_posts(*, ticker: str, subreddit: str, query: str) -> list[RedditPost]:
    qs = urlencode(
        {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "t": "year",
            "limit": 100,
        }
    )
    url = f"https://www.reddit.com/r/{quote(subreddit)}/search.rss?{qs}"
    request = Request(url, headers=REDDIT_HEADERS)
    for attempt in range(len(REDDIT_HTTP_429_RETRY_DELAYS) + 1):
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read()
            return parse_reddit_atom(payload, ticker=ticker, subreddit=subreddit)
        except HTTPError as exc:
            if exc.code == 429 and attempt < len(REDDIT_HTTP_429_RETRY_DELAYS):
                # Prefer Reddit's own Retry-After hint; it is often longer than
                # our fixed backoff, so honoring it stops retries from expiring
                # inside a single cooldown window.
                delay = _retry_after_seconds(exc) or REDDIT_HTTP_429_RETRY_DELAYS[attempt]
                print(
                    f"warning: Reddit RSS {ticker} r/{subreddit} query={query!r} "
                    f"HTTP 429; retrying in {delay:.0f}s"
                )
                time.sleep(delay)
                continue
            print(
                f"warning: Reddit RSS {ticker} r/{subreddit} query={query!r} "
                f"HTTP {exc.code}"
            )
            return []
        except (URLError, TimeoutError) as exc:
            print(f"warning: Reddit RSS {ticker} r/{subreddit} query={query!r} failed: {exc}")
            return []
    return []


def fetch_trading_days(start_date: date, end_date: date, benchmark: str) -> list[date]:
    frame = yf.download(
        benchmark,
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=False,
    )
    if frame.empty:
        return []
    return [idx.date() for idx in frame.index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan Reddit RSS coverage for Plan B backtest quarters."
    )
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--lookback-days", type=int, default=7)
    args = parser.parse_args(argv)

    settings = get_settings()
    tickers = tuple(settings.evaluation.tickers)
    subreddits = tuple(settings.sentiment.reddit_subreddits)
    queries = {ticker: DEFAULT_QUERY_ALIASES.get(ticker, (ticker,)) for ticker in tickers}
    posts = fetch_all_posts(
        tickers=tickers,
        subreddits=subreddits,
        queries=queries,
        request_delay_seconds=args.delay,
    )
    trading_days = {
        candidate.name: fetch_trading_days(
            candidate.start_date,
            candidate.end_date,
            settings.evaluation.benchmark,
        )
        for candidate in DEFAULT_CANDIDATES
    }
    scores = score_candidate_quarters(
        DEFAULT_CANDIDATES,
        posts,
        tickers=tickers,
        subreddits=subreddits,
        trading_days_by_quarter=trading_days,
        lookback_days=args.lookback_days,
    )
    print("Plan B Reddit coverage scan")
    pair_count = len(tickers) * len(subreddits)
    for index, score in enumerate(scores, start=1):
        pct1 = 100 * score.covered_ticker_days_at_least_1 / max(score.ticker_day_count, 1)
        pct3 = 100 * score.covered_ticker_days_at_least_3 / max(score.ticker_day_count, 1)
        print(
            f"{index}. {score.quarter}: posts={score.total_posts}, "
            f">=1 coverage={pct1:.1f}%, >=3 coverage={pct3:.1f}%, "
            f"min ticker coverage={100 * score.min_ticker_coverage_at_least_1:.1f}%, "
            f"pairs={score.nonzero_ticker_subreddit_pairs}/{pair_count}"
        )
    if scores:
        print(f"Recommended Plan B period: {scores[0].quarter}")
    return 0


def _dedupe_key(post: RedditPost) -> str:
    match = re.search(r"/comments/([^/]+)/", post.url)
    if match:
        return match.group(1)
    return post.url or f"{post.published_at.isoformat()}:{post.title}"


def _score_one_candidate(
    candidate: CandidateQuarter,
    posts: list[RedditPost],
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    trading_days: list[date],
    lookback_days: int,
) -> CoverageScore:
    quarter_posts = [
        post
        for post in posts
        if candidate.start_date <= post.published_date <= candidate.end_date
        and post.ticker in tickers
        and post.subreddit in subreddits
    ]
    posts_by_ticker: dict[str, list[RedditPost]] = defaultdict(list)
    pairs: set[tuple[str, str]] = set()
    for post in quarter_posts:
        posts_by_ticker[post.ticker].append(post)
        pairs.add((post.ticker, post.subreddit))

    covered_1 = 0
    covered_3 = 0
    ticker_covered_counts: dict[str, int] = {ticker: 0 for ticker in tickers}
    for ticker in tickers:
        for trade_date in trading_days:
            start = trade_date - timedelta(days=lookback_days)
            count = sum(
                1
                for post in posts_by_ticker.get(ticker, [])
                if start <= post.published_date <= trade_date
            )
            if count >= 1:
                covered_1 += 1
                ticker_covered_counts[ticker] += 1
            if count >= 3:
                covered_3 += 1

    trading_day_count = len(trading_days)
    if trading_day_count == 0:
        min_ticker_coverage = 0.0
    else:
        min_ticker_coverage = min(
            (ticker_covered_counts[ticker] / trading_day_count for ticker in tickers),
            default=0.0,
        )
    return CoverageScore(
        quarter=candidate.name,
        total_posts=len(quarter_posts),
        ticker_day_count=len(tickers) * trading_day_count,
        covered_ticker_days_at_least_1=covered_1,
        covered_ticker_days_at_least_3=covered_3,
        min_ticker_coverage_at_least_1=min_ticker_coverage,
        nonzero_ticker_subreddit_pairs=len(pairs),
    )


def _retry_after_seconds(exc: HTTPError) -> float | None:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if not retry_after:
            return None
        return min(float(retry_after), 60.0)
    except (TypeError, ValueError, AttributeError):
        return None


def _parse_atom_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _strip_reddit_html(value: str) -> str:
    content = html.unescape(str(value or ""))
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->", 1)[1].split("<!-- SC_ON -->", 1)[0]
    return _one_line(re.sub(r"<[^>]+>", " ", content))


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


if __name__ == "__main__":
    raise SystemExit(main())
