from datetime import timedelta
from typing import Any, Type

import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class NewsInput(BaseModel):
    """Input schema for ticker or query news."""

    query: str = Field(..., description="Ticker symbol or company/news query.")
    start_date: str | None = Field(None, description="Inclusive start date in YYYY-MM-DD format.")
    end_date: str | None = Field(None, description="Inclusive end date in YYYY-MM-DD format.")
    limit: int = Field(10, description="Maximum number of headlines to return.")


class GlobalNewsInput(BaseModel):
    """Input schema for broad market news."""

    curr_date: str = Field(..., description="Current date in YYYY-MM-DD format.")
    look_back_days: int = Field(7, description="Number of calendar days to look back.")
    limit: int = Field(10, description="Maximum number of headlines to return.")


class GetNewsTool(BaseTool):
    name: str = "get_news"
    description: str = (
        "Fetches company-specific or query-specific Yahoo Finance headlines with timestamps, "
        "publisher/source, and URLs when available."
    )
    args_schema: Type[BaseModel] = NewsInput

    def _run(
        self,
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 10,
    ) -> str:
        return get_news_text(query, start_date, end_date, limit)


class GetGlobalNewsTool(BaseTool):
    name: str = "get_global_news"
    description: str = (
        "Fetches broad market headlines from Yahoo Finance index ticker feeds. "
        "The result explicitly notes this source limitation."
    )
    args_schema: Type[BaseModel] = GlobalNewsInput

    def _run(self, curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
        return get_global_news_text(curr_date, look_back_days, limit)


def get_news_text(
    query: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
) -> str:
    clean_query = query.strip()
    try:
        items = list(getattr(yf.Ticker(clean_query), "news", None) or [])
    except Exception as exc:
        return f"No news data available for {clean_query}. Upstream error: {exc}"

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    records = _filter_records((_normalise_news_item(item) for item in items), start, end)
    records = records[: max(limit, 0)]
    if not records:
        return f"No news data available for {clean_query} between {start_date} and {end_date}."

    lines = [
        f"News for {clean_query} between {start_date or 'unbounded'} and {end_date or 'unbounded'}."
    ]
    lines.extend(_format_record(index, record) for index, record in enumerate(records, start=1))
    return "\n".join(lines)


def get_global_news_text(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    end = _parse_date(curr_date) or pd.Timestamp.utcnow().normalize().tz_localize(None)
    start = end - timedelta(days=max(look_back_days, 0))
    collected: list[dict[str, Any]] = []
    for symbol in ["^GSPC", "^IXIC", "^DJI"]:
        try:
            items = getattr(yf.Ticker(symbol), "news", None) or []
        except Exception:
            items = []
        collected.extend(_normalise_news_item(item, source_symbol=symbol) for item in items)

    records = _filter_records(collected, start, end)
    records = _dedupe_records(records)[: max(limit, 0)]
    if not records:
        return (
            "Source limitation: global news currently uses Yahoo Finance index ticker feeds "
            f"(^GSPC, ^IXIC, ^DJI). No global news data available between "
            f"{start.strftime('%Y-%m-%d')} and {end.strftime('%Y-%m-%d')}."
        )

    lines = [
        "Source limitation: global news currently uses Yahoo Finance index ticker feeds "
        "(^GSPC, ^IXIC, ^DJI).",
        f"Global market news from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}.",
    ]
    lines.extend(_format_record(index, record) for index, record in enumerate(records, start=1))
    return "\n".join(lines)


def _normalise_news_item(item: dict[str, Any], source_symbol: str | None = None) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    canonical_url = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    click_through = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
    timestamp = (
        item.get("providerPublishTime")
        or content.get("pubDate")
        or content.get("displayTime")
        or item.get("pubDate")
    )
    return {
        "title": item.get("title") or content.get("title") or "Untitled headline",
        "publisher": (
            item.get("publisher")
            or provider.get("displayName")
            or item.get("source")
            or source_symbol
            or "Unknown source"
        ),
        "published_at": _parse_news_timestamp(timestamp),
        "url": item.get("link") or canonical_url.get("url") or click_through.get("url"),
    }


def _filter_records(
    records: list[dict[str, Any]] | Any,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> list[dict[str, Any]]:
    filtered = []
    for record in records:
        published_at = record.get("published_at")
        if published_at is not None:
            if start is not None and published_at < start:
                continue
            if end is not None and published_at > end + timedelta(days=1):
                continue
        filtered.append(record)
    return sorted(
        filtered,
        key=lambda record: record.get("published_at") or pd.Timestamp.min,
        reverse=True,
    )


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None]] = set()
    deduped = []
    for record in records:
        key = (record.get("title", ""), record.get("url"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _format_record(index: int, record: dict[str, Any]) -> str:
    timestamp = record.get("published_at")
    if timestamp is None:
        date_text = "unknown date"
    else:
        date_text = timestamp.strftime("%Y-%m-%d %H:%M")
    url = record.get("url") or "No URL available"
    return (
        f"{index}. {date_text} - {record.get('publisher', 'Unknown source')} - "
        f"{record.get('title', 'Untitled headline')} - {url}"
    )


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
