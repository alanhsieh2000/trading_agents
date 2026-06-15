import html
import json
import re
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from trading_agents.config import get_settings


REDDIT_HEADERS = {
    "User-Agent": "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)",
    "Accept": "application/atom+xml, application/rss+xml, text/xml, */*",
}
REDDIT_JSON_HEADERS = {
    "User-Agent": "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)",
    "Accept": "application/json",
}
STOCKTWITS_HEADERS = {
    "User-Agent": "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)",
    "Accept": "application/json",
}
SECONDS_PER_WEEK = 7 * 24 * 60 * 60
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_stocktwits_messages(
    ticker: str,
    limit: int | None = None,
    timeout: float | None = None,
) -> str:
    settings = get_settings().sentiment
    effective_limit = settings.stocktwits_limit if limit is None else limit
    effective_timeout = settings.stocktwits_timeout if timeout is None else timeout
    symbol = ticker.upper().strip()
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{quote(symbol)}.json?limit={effective_limit}"
    try:
        payload = _fetch_json(url, headers=STOCKTWITS_HEADERS, timeout=effective_timeout)
    except Exception:
        return f"No data available for StockTwits messages for {symbol}."

    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not messages:
        return f"No data available for StockTwits messages for {symbol}."

    lines = []
    bullish = bearish = unlabeled = 0
    for message in messages[: max(effective_limit, 0)]:
        sentiment_obj = ((message.get("entities") or {}).get("sentiment") or {})
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"

        created = message.get("created_at", "")
        user = (message.get("user") or {}).get("username", "?")
        body = _trim_text(_one_line(message.get("body", "")), 280)
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)


def fetch_reddit_posts(
    query: str,
    limit: int | None = None,
    subreddits: Iterable[str] | None = None,
    limit_per_sub: int | None = None,
    timeout: float | None = None,
    inter_request_delay: float | None = None,
) -> str:
    settings = get_settings().sentiment
    effective_subreddits = tuple(settings.reddit_subreddits if subreddits is None else subreddits)
    effective_limit_per_sub = settings.reddit_limit_per_sub if limit_per_sub is None else limit_per_sub
    effective_timeout = settings.reddit_timeout if timeout is None else timeout
    effective_delay = (
        settings.reddit_inter_request_delay
        if inter_request_delay is None
        else inter_request_delay
    )
    effective_limit = max(effective_limit_per_sub if limit is None else limit, 0)
    clean_query = query.strip()
    blocks = []
    total_posts = 0
    now = time.time()

    for index, subreddit in enumerate(effective_subreddits):
        if index > 0 and effective_delay > 0:
            time.sleep(effective_delay)

        try:
            posts = _fetch_subreddit_posts(clean_query, subreddit, effective_limit, effective_timeout)
        except Exception:
            posts = []

        posts = [
            post
            for post in posts
            if _is_quality_recent_reddit_post(
                post,
                now=now,
                min_score=settings.reddit_min_score,
                min_comments=settings.reddit_min_comments,
                recency_window_seconds=settings.reddit_recency_window_seconds,
            )
        ][:effective_limit]
        total_posts += len(posts)

        if not posts:
            blocks.append(f"r/{subreddit}: ")
            continue

        via_rss = any(post.get("source") == "rss" for post in posts)
        header = f"r/{subreddit} — {len(posts)} recent posts mentioning {clean_query.upper()}"
        if via_rss:
            header += " (via RSS feed; scores/comments unavailable):"
        else:
            header += ":"
        lines = [header]
        for post in posts:
            title = _one_line(post.get("title", ""))
            score = post.get("score")
            comments = post.get("num_comments")
            created = post.get("created_utc")
            created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            meta = created_str
            if score is not None and comments is not None:
                meta += f" · {_as_int(score):>4}↑ · {_as_int(comments):>3}c"
            selftext = _trim_text(_one_line(post.get("selftext", "")), 240)
            lines.append(
                f" [{meta}] {title}"
                + (f"\n body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return f"No data available for Reddit posts for {clean_query}."

    return "\n\n".join(blocks)


def _fetch_subreddit_posts(
    query: str,
    subreddit: str,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    """Fetch Reddit search results through RSS/Atom.

    Reddit's public ``search.json`` endpoint is frequently WAF-blocked for
    unauthenticated clients. The RSS search feed is less rich but does not
    require an API key, so it is the default path for live sentiment context.
    """
    url = _subreddit_search_url("rss", query, subreddit, limit)
    return _fetch_subreddit_rss(url, timeout=timeout, limit=max(limit, 0))


def _fetch_subreddit_json(
    query: str,
    subreddit: str,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    """Fetch Reddit JSON search results when the endpoint is usable.

    This path carries richer score/comment metadata than RSS. It is kept for a
    future OAuth-backed or unblocked JSON path, but it is not the default public
    fetch because Reddit currently blocks unauthenticated ``search.json``.
    """
    url = _subreddit_search_url("json", query, subreddit, limit)
    payload = _fetch_json(url, headers=REDDIT_JSON_HEADERS, timeout=timeout)
    children = (
        ((payload.get("data") or {}).get("children") or [])
        if isinstance(payload, dict)
        else []
    )
    posts = []
    for child in children:
        if not isinstance(child, dict):
            continue
        data = child.get("data") or {}
        if isinstance(data, dict):
            post = dict(data)
            post["source"] = "json"
            posts.append(post)
    return posts


def _subreddit_search_url(
    suffix: str,
    query: str,
    subreddit: str,
    limit: int,
) -> str:
    qs = urlencode(
        {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",
            "limit": max(limit, 0),
        }
    )
    return f"https://www.reddit.com/r/{quote(subreddit)}/search.{suffix}?{qs}"


def _fetch_subreddit_rss(
    url: str,
    timeout: float,
    limit: int,
    retry: bool = True,
) -> list[dict[str, Any]]:
    request = Request(url, headers=REDDIT_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            root = ET.fromstring(response.read())
    except HTTPError as exc:
        if exc.code == 429 and retry:
            wait = _retry_after_seconds(exc) or 5.0
            time.sleep(wait)
            return _fetch_subreddit_rss(
                url,
                timeout=timeout,
                limit=limit,
                retry=False,
            )
        return []
    except (URLError, TimeoutError, ET.ParseError):
        return []

    posts = []
    for entry in root.findall("atom:entry", ATOM_NS)[:limit]:
        title = entry.find("atom:title", ATOM_NS)
        published = entry.find("atom:published", ATOM_NS)
        content = entry.find("atom:content", ATOM_NS)
        posts.append(
            {
                "title": title.text if title is not None and title.text else "",
                "score": None,
                "num_comments": None,
                "created_utc": _parse_atom_timestamp(
                    published.text if published is not None else None
                ),
                "selftext": _strip_reddit_html(
                    content.text if content is not None and content.text else ""
                ),
                "source": "rss",
            }
        )
    return posts


def _is_quality_recent_reddit_post(
    post: dict[str, Any],
    now: float,
    min_score: int,
    min_comments: int,
    recency_window_seconds: int,
) -> bool:
    created = post.get("created_utc")
    try:
        created_timestamp = float(created)
    except (TypeError, ValueError):
        return False
    if not now - recency_window_seconds <= created_timestamp <= now:
        return False
    if post.get("source") == "rss" and (
        post.get("score") is None or post.get("num_comments") is None
    ):
        return True
    return (
        _as_int(post.get("score")) > min_score
        and _as_int(post.get("num_comments")) > min_comments
    )


def _parse_atom_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def _strip_reddit_html(value: str) -> str:
    if not value:
        return ""
    content = str(value)
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->", 1)[1].split("<!-- SC_ON -->", 1)[0]
    text = re.sub(r"<[^>]+>", " ", content)
    return _one_line(html.unescape(text))


def _retry_after_seconds(exc: HTTPError) -> float | None:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if not retry_after:
            return None
        return min(float(retry_after), 30.0)
    except (TypeError, ValueError, AttributeError):
        return None


def _fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not fetch JSON from {url}") from exc


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def _trim_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 1:
        return value[:max_length]
    return value[:max_length] + "…"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
