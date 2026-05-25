import json
import time
from collections.abc import Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")
REDDIT_HEADERS = {"User-Agent": "trading-agents/0.1"}
MIN_REDDIT_SCORE = 4
MIN_REDDIT_COMMENTS = 3
SECONDS_PER_WEEK = 7 * 24 * 60 * 60


def fetch_stocktwits_messages(ticker: str, limit: int = 30) -> str:
    symbol = ticker.upper().strip()
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{quote(symbol)}.json?limit={limit}"
    try:
        payload = _fetch_json(url)
    except Exception:
        return f"No data available for StockTwits messages for {symbol}."

    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not messages:
        return f"No data available for StockTwits messages for {symbol}."

    lines = []
    bullish = bearish = unlabeled = 0
    for message in messages[: max(limit, 0)]:
        sentiment_obj = ((message.get("entities") or {}).get("sentiment") or {})
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        if sentiment == "Bullish":
            bullish += 1
            sentiment_label = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            sentiment_label = "Bearish"
        else:
            unlabeled += 1
            sentiment_label = "no-label"

        user = (message.get("user") or {}).get("username", "unknown")
        created_at = message.get("created_at", "unknown date")
        body = _trim_text(_one_line(message.get("body", "")), 280)
        lines.append(f"[{created_at} - @{user} - {sentiment_label}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) - "
        f"Bearish: {bearish} ({bear_pct}%) - "
        f"Unlabeled: {unlabeled} - "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)


def fetch_reddit_posts(
    query: str,
    limit: int | None = None,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
) -> str:
    clean_query = query.strip()
    effective_limit = min(max(limit_per_sub if limit is None else limit, 0), 5)
    subreddit_list = tuple(subreddits)
    blocks = []
    total_posts = 0

    for subreddit in subreddit_list:
        try:
            posts = _fetch_subreddit_posts(clean_query, subreddit, effective_limit)
        except Exception:
            posts = []

        qualified_posts = [
            post
            for post in posts
            if _is_quality_recent_reddit_post(post, now=time.time())
        ][:effective_limit]
        total_posts += len(qualified_posts)

        if not qualified_posts:
            blocks.append(
                f"r/{subreddit}: <no high-quality posts found mentioning "
                f"{clean_query.upper()} in the past 7 days>"
            )
            continue

        lines = [
            f"r/{subreddit} - {len(qualified_posts)} high-quality recent posts "
            f"mentioning {clean_query.upper()}:"
        ]
        for post in qualified_posts:
            title = _one_line(post.get("title", "Untitled post"))
            score = _as_int(post.get("score"))
            comments = _as_int(post.get("num_comments"))
            created = post.get("created_utc")
            created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            selftext = _trim_text(_one_line(post.get("selftext", "")), 240)
            lines.append(
                f" [{created_str} - {score:>4} upvotes - {comments:>3} comments] {title}"
                + (f"\n body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        subreddits_text = ", ".join(f"r/{subreddit}" for subreddit in subreddit_list)
        return (
            f"No data available for Reddit posts for {clean_query}. "
            f"No high-quality posts found across {subreddits_text} in the past 7 days."
        )

    return "\n\n".join(blocks)


def _fetch_subreddit_posts(query: str, subreddit: str, limit: int) -> list[dict[str, Any]]:
    qs = urlencode(
        {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",
            "limit": max(limit, 0),
        }
    )
    url = f"https://www.reddit.com/r/{quote(subreddit)}/search.json?{qs}"
    payload = _fetch_json(url, headers=REDDIT_HEADERS)
    children = ((payload.get("data") or {}).get("children") or []) if isinstance(payload, dict) else []
    return [child.get("data") or {} for child in children if isinstance(child, dict)]


def _is_quality_recent_reddit_post(post: dict[str, Any], now: float) -> bool:
    created = post.get("created_utc")
    try:
        created_timestamp = float(created)
    except (TypeError, ValueError):
        return False
    return (
        now - SECONDS_PER_WEEK <= created_timestamp <= now
        and _as_int(post.get("score")) > MIN_REDDIT_SCORE
        and _as_int(post.get("num_comments")) > MIN_REDDIT_COMMENTS
    )


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not fetch JSON from {url}") from exc


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def _trim_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return value[: max_length - 3] + "..."


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
