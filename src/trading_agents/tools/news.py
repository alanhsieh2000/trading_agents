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
        "Fetches company-specific or query-specific Yahoo Finance headlines with title, "
        "publisher, publish date, summary, and link when available."
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
    click_through = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    timestamp = content.get("pubDate") or item.get("providerPublishTime") or item.get("pubDate")
    return {
        "title": content.get("title") or item.get("title") or "No title",
        "publisher": (
            provider.get("displayName")
            or item.get("publisher")
            or item.get("source")
            or source_symbol
            or "Unknown"
        ),
        "pub_date": _parse_news_timestamp(timestamp),
        "summary": content.get("summary") or item.get("summary") or "",
        "link": canonical_url.get("url") or click_through.get("url") or item.get("link") or "",
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


def _format_record(index: int, record: dict[str, Any]) -> str:
    pub_date = record.get("pub_date")
    date_text = pub_date.strftime("%Y-%m-%d %H:%M") if pub_date is not None else "unknown date"
    title = record.get("title", "No title")
    publisher = record.get("publisher", "Unknown")
    lines = [
        f"{index}. {title} (source: {publisher})",
        f"Published: {date_text}",
    ]
    summary = record.get("summary")
    if summary:
        lines.append(str(summary))
    link = record.get("link")
    if link:
        lines.append(f"Link: {link}")
    return "\n".join(lines)


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
