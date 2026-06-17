"""Historical news and social sources for the evaluation dataset builder.

The live analyst tools use yfinance, Reddit, and StockTwits endpoints that do
not support arbitrary historical windows. The dataset builder uses this module
instead, querying Exa with published-date filters and rendering text blocks that
look like the existing analyst tool outputs.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from exa_py import Exa
import exa_py.api as exa_api

from trading_agents.tools.news import _format_news_block, _parse_news_timestamp
from trading_agents.tools.sentiment import _one_line, _trim_text


load_dotenv()

EXA_API_KEY_ENV = "EXA_API_KEY"
EXA_REQUEST_TIMEOUT_SECONDS = 20


def fetch_news_via_exa(query: str, start_date: str, end_date: str, limit: int) -> str:
    """Fetch historical company/query news through Exa."""
    clean_query = query.strip()
    records = _search_news_records(
        f"{clean_query} stock company news",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not records:
        return f"No news found for {clean_query} between {start_date} and {end_date}"

    return _format_news_block(
        heading=f"## {clean_query} News, from {start_date} to {end_date}:",
        records=records,
    )


def fetch_global_news_via_exa(curr_date: str, look_back_days: int, limit: int) -> str:
    """Fetch historical global market news through Exa."""
    end = _parse_date(curr_date)
    start = end - timedelta(days=max(look_back_days, 0))
    start_date = start.strftime("%Y-%m-%d")
    end_date = end.strftime("%Y-%m-%d")
    records = _search_news_records(
        "global stock market news economy macro financial markets",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not records:
        return f"No global news found for {curr_date}"

    return _format_news_block(
        heading=f"## Global Market News, from {start_date} to {end_date}:",
        records=records,
    )


def fetch_reddit_via_exa(
    ticker: str, start_date: str, end_date: str, limit: int
) -> str:
    """Fetch historical Reddit posts mentioning ``ticker`` through Exa."""
    symbol = ticker.upper().strip()
    results = _search(
        f"{symbol} stock investing discussion",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        include_domains=["reddit.com"],
    )
    if not results:
        return f"No data available for Reddit posts for {symbol}."

    lines = [f"Reddit posts mentioning {symbol} from {start_date} to {end_date}:"]
    for result in results[: max(limit, 0)]:
        title = _one_line(_result_attr(result, "title") or "Untitled Reddit post")
        published = _published_date_label(result)
        body = _trim_text(_one_line(_result_excerpt(result)), 240)
        url = _result_attr(result, "url")
        line = f" [{published}] {title}"
        if body:
            line += f"\n body excerpt: {body}"
        if url:
            line += f"\n link: {url}"
        lines.append(line)
    return "\n".join(lines)


def fetch_stocktwits_via_exa(
    ticker: str, start_date: str, end_date: str, limit: int
) -> str:
    """Fetch historical StockTwits messages mentioning ``ticker`` through Exa."""
    symbol = ticker.upper().strip()
    results = _search(
        f"${symbol} stocktwits stock sentiment",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        include_domains=["stocktwits.com"],
    )
    if not results:
        return f"No data available for StockTwits messages for {symbol}."

    lines = []
    for result in results[: max(limit, 0)]:
        title = _one_line(_result_attr(result, "title") or "StockTwits message")
        published = _published_date_label(result)
        body = _trim_text(_one_line(_result_excerpt(result)), 280)
        url = _result_attr(result, "url")
        line = f"[{published} | no-label] {title}"
        if body:
            line += f" - {body}"
        if url:
            line += f" ({url})"
        lines.append(line)

    summary = f"Total: {len(lines)} historical StockTwits results for {symbol}"
    return summary + "\n\n" + "\n".join(lines)


def _search_news_records(
    query: str, *, start_date: str, end_date: str, limit: int
) -> list[dict[str, Any]]:
    results = _search(
        query,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        category="news",
    )
    records = [_normalise_exa_news_result(result) for result in results]
    records = [record for record in records if record["title"] or record["link"]]
    return sorted(
        records,
        key=lambda record: record.get("pub_date") or pd.Timestamp.min,
        reverse=True,
    )[: max(limit, 0)]


def _search(
    query: str,
    *,
    start_date: str,
    end_date: str,
    limit: int,
    include_domains: list[str] | None = None,
    category: str | None = None,
) -> list[Any]:
    response = _get_exa_client().search(
        query,
        num_results=max(limit, 0),
        include_domains=include_domains,
        start_published_date=start_date,
        end_published_date=end_date,
        category=category,
        contents={
            "text": {"max_characters": 500},
            "summary": {"query": query},
        },
    )
    return list(getattr(response, "results", None) or [])


def _get_exa_client() -> Exa:
    api_key = os.environ.get(EXA_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(
            "EXA_API_KEY is required to build evaluation news/social sources. "
            "Add it to .env or export it in the environment."
        )
    client = Exa(api_key=api_key)
    original_request = getattr(client, "request", None)
    if original_request is None:
        return client

    def request_with_timeout(*args: Any, **kwargs: Any) -> Any:
        with _exa_request_timeout_patch():
            return original_request(*args, **kwargs)

    client.request = request_with_timeout
    return client


@contextmanager
def _exa_request_timeout_patch() -> Any:
    """Temporarily add bounded timeouts to the Exa SDK's requests calls."""
    original_get = exa_api.requests.get
    original_post = exa_api.requests.post
    original_patch = exa_api.requests.patch
    original_delete = exa_api.requests.delete

    def _ensure_timeout(kwargs: dict[str, Any]) -> None:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = EXA_REQUEST_TIMEOUT_SECONDS

    def get_with_timeout(*args: Any, **kwargs: Any) -> Any:
        _ensure_timeout(kwargs)
        return original_get(*args, **kwargs)

    def post_with_timeout(*args: Any, **kwargs: Any) -> Any:
        _ensure_timeout(kwargs)
        return original_post(*args, **kwargs)

    def patch_with_timeout(*args: Any, **kwargs: Any) -> Any:
        _ensure_timeout(kwargs)
        return original_patch(*args, **kwargs)

    def delete_with_timeout(*args: Any, **kwargs: Any) -> Any:
        _ensure_timeout(kwargs)
        return original_delete(*args, **kwargs)

    exa_api.requests.get = get_with_timeout
    exa_api.requests.post = post_with_timeout
    exa_api.requests.patch = patch_with_timeout
    exa_api.requests.delete = delete_with_timeout
    try:
        yield
    finally:
        exa_api.requests.get = original_get
        exa_api.requests.post = original_post
        exa_api.requests.patch = original_patch
        exa_api.requests.delete = original_delete


def _normalise_exa_news_result(result: Any) -> dict[str, Any]:
    url = _result_attr(result, "url")
    return {
        "title": _result_attr(result, "title") or "No title",
        "summary": _result_excerpt(result),
        "publisher": _result_attr(result, "author") or _domain_label(url) or "Unknown",
        "link": url,
        "pub_date": _parse_news_timestamp(_result_attr(result, "published_date")),
    }


def _result_excerpt(result: Any) -> str:
    summary = _result_attr(result, "summary")
    if summary:
        return str(summary)
    highlights = _result_attr(result, "highlights")
    if highlights:
        return " ".join(str(item) for item in highlights if item)
    text = _result_attr(result, "text")
    if text:
        return _trim_text(_one_line(str(text)), 500)
    return ""


def _result_attr(result: Any, name: str) -> Any:
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


def _published_date_label(result: Any) -> str:
    parsed = _parse_news_timestamp(_result_attr(result, "published_date"))
    if parsed is None:
        return "?"
    return parsed.strftime("%Y-%m-%d")


def _domain_label(url: str | None) -> str:
    if not url:
        return ""
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")
