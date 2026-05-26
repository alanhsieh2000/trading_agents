from datetime import timedelta
from typing import Any, Type

import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from trading_agents.config import get_settings


class NewsInput(BaseModel):
    """Input schema for ticker or query news."""

    query: str = Field(..., description="Ticker symbol or company/news query.")
    start_date: str | None = Field(None, description="Inclusive start date in YYYY-MM-DD format.")
    end_date: str | None = Field(None, description="Inclusive end date in YYYY-MM-DD format.")
    limit: int | None = Field(None, description="Maximum number of headlines to return.")


class GlobalNewsInput(BaseModel):
    """Input schema for broad market news."""

    curr_date: str = Field(..., description="Current date in YYYY-MM-DD format.")
    look_back_days: int | None = Field(None, description="Number of calendar days to look back.")
    limit: int | None = Field(None, description="Maximum number of headlines to return.")


class GetNewsTool(BaseTool):
    name: str = "get_news"
    description: str = (
        "Fetches company-specific or query-specific Yahoo Finance headlines with title, "
        "publisher, publish date, summary, and link when available."
    )
    args_schema: Type[BaseModel] = NewsInput

    def _run(
        self,
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> str:
        return get_news_text(query, start_date, end_date, limit)


class GetGlobalNewsTool(BaseTool):
    name: str = "get_global_news"
    description: str = (
        "Fetches broad market headlines from Yahoo Finance index ticker feeds. "
        "Returns compact article summaries and links."
    )
    args_schema: Type[BaseModel] = GlobalNewsInput

    def _run(
        self,
        curr_date: str,
        look_back_days: int | None = None,
        limit: int | None = None,
    ) -> str:
        return get_global_news_text(curr_date, look_back_days, limit)


def get_news_text(
    query: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> str:
    clean_query = query.strip()
    effective_limit = get_settings().news.ticker_limit if limit is None else limit
    try:
        items = list(getattr(yf.Ticker(clean_query), "news", None) or [])
    except Exception as exc:
        return f"Error fetching news for {clean_query}: {exc}"

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    records = _filter_records((_normalise_news_item(item) for item in items), start, end)
    records = records[: max(effective_limit, 0)]
    if not records:
        if start_date and end_date:
            return f"No news found for {clean_query} between {start_date} and {end_date}"
        return f"No news found for {clean_query}"

    return _format_news_block(
        heading=f"## {clean_query} News, from {start_date or 'unbounded'} to {end_date or 'unbounded'}:",
        records=records,
    )


def get_global_news_text(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    settings = get_settings().news
    effective_lookback = settings.global_lookback_days if look_back_days is None else look_back_days
    effective_limit = settings.global_limit if limit is None else limit
    end = _parse_date(curr_date) or pd.Timestamp.utcnow().normalize().tz_localize(None)
    start = end - timedelta(days=max(effective_lookback, 0))
    collected: list[dict[str, Any]] = []
    for symbol in settings.global_index_symbols:
        try:
            items = getattr(yf.Ticker(symbol), "news", None) or []
        except Exception:
            items = []
        collected.extend(_normalise_news_item(item, source_symbol=symbol) for item in items)

    records = _filter_records(collected, start, end)
    records = _dedupe_records(records)[: max(effective_limit, 0)]
    if not records:
        return f"No global news found for {curr_date}"

    return _format_news_block(
        heading=(
            "## Global Market News, from "
            f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}:"
        ),
        records=records,
    )


def _normalise_news_item(item: dict[str, Any], source_symbol: str | None = None) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    canonical_url = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
    click_through = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
    timestamp = content.get("pubDate") or item.get("providerPublishTime") or item.get("pubDate")
    return {
        "title": content.get("title") or item.get("title") or "No title",
        "summary": content.get("summary") or item.get("summary") or "",
        "publisher": (
            provider.get("displayName")
            or item.get("publisher")
            or item.get("source")
            or source_symbol
            or "Unknown"
        ),
        "link": canonical_url.get("url") or click_through.get("url") or item.get("link") or "",
        "pub_date": _parse_news_timestamp(timestamp),
    }


def _filter_records(
    records: list[dict[str, Any]] | Any,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> list[dict[str, Any]]:
    filtered = []
    for record in records:
        pub_date = record.get("pub_date")
        if pub_date is not None:
            if start is not None and pub_date < start:
                continue
            if end is not None and pub_date > end + timedelta(days=1):
                continue
        filtered.append(record)
    return sorted(
        filtered,
        key=lambda record: record.get("pub_date") or pd.Timestamp.min,
        reverse=True,
    )


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for record in records:
        key = (record.get("title", ""), record.get("link", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _format_news_block(heading: str, records: list[dict[str, Any]]) -> str:
    articles = []
    for record in records:
        article_lines = [f"### {record.get('title', 'No title')} (source: {record.get('publisher', 'Unknown')})"]
        summary = record.get("summary")
        if summary:
            article_lines.append(str(summary))
        link = record.get("link")
        if link:
            article_lines.append(f"Link: {link}")
        articles.append("\n".join(article_lines))
    return heading + "\n\n" + "\n\n".join(articles) + "\n"


def _parse_news_timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return pd.to_datetime(value, unit="s", utc=True).tz_convert(None)
        return pd.to_datetime(value, utc=True).tz_convert(None)
    except Exception:
        return None


def _parse_date(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return pd.to_datetime(value, utc=True).tz_convert(None).normalize()
    except Exception:
        return None


get_news = GetNewsTool()
get_global_news = GetGlobalNewsTool()
