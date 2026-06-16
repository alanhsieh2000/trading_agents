from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


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
