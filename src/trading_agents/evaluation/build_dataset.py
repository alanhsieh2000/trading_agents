"""CLI support for building prepared evaluation datasets.

This module owns the shared dataset-building pieces for both the canonical
Plan 07 evaluation and the Plan B evaluation. The two entry points differ only
in their default date window and dataset path; the write paths are shared so the
backtest mechanics remain comparable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd
import yfinance as yf

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation.exa_sources import (
    fetch_global_news_via_exa,
    fetch_news_via_exa,
)
from trading_agents.evaluation.reddit_coverage import (
    DEFAULT_QUERY_ALIASES,
    RedditPost,
    fetch_rss_posts,
)
from trading_agents.evaluation.sec_sources import (
    ensure_sec_archive,
    render_point_in_time_fundamentals,
)
from trading_agents.tools.fundamentals import get_statement_text
from trading_agents.tools.market_data import (
    ALLOWED_INDICATORS,
    INDICATOR_MIN_WARMUP_ROWS,
    _normalise_price_history,
    download_indicator_history,
    get_stock_data_text,
    render_indicators_text,
)


PLAN_B_START_DATE = "2026-01-01"
PLAN_B_END_DATE = "2026-03-31"
PLAN_B_BUFFER_START_DATE = "2025-12-01"
PLAN_B_DATASET_PATH = "data/eval_dataset_2026q1.duckdb"
ARCTIC_SHIFT_RAW_DIR = Path("data/raw-backtest/arctic-shift")
STOCKTWITS_RAW_DIR = Path("data/raw-backtest/stocktwits")


@dataclass(frozen=True)
class BuildDatasetOptions:
    dataset_path: str
    tickers: tuple[str, ...]
    benchmark: str
    start_date: str
    end_date: str
    buffer_start_date: str
    price_tail_days: int
    lookback_days: int
    weight_over: float
    weight_under: float
    limit_days: int | None
    verify_only: bool
    news_limit: int = 40
    global_news_limit: int = 20
    global_news_lookback_days: int = 7
    reddit_limit_per_sub: int = 5
    reddit_request_delay_seconds: float = 10.0
    use_arctic_shift_reddit: bool = False


@dataclass(frozen=True)
class PriceBuildResult:
    symbols: tuple[str, ...]
    rows_by_symbol: dict[str, int]
    transaction_days: tuple[str, ...]
    fetch_start_date: str
    fetch_end_date: str


@dataclass(frozen=True)
class ToolOutputBuildResult:
    tool_name: str
    symbols: tuple[str, ...]
    payloads_written: int
    transaction_days: tuple[str, ...]
    lookback_days: int


@dataclass(frozen=True)
class RedditBuildResult:
    tool_name: str
    symbols: tuple[str, ...]
    subreddits: tuple[str, ...]
    posts_written: int
    payloads_written: int
    transaction_days: tuple[str, ...]
    lookback_days: int
    payload_limit_per_sub: int
    request_delay_seconds: float
    source: str = "reddit-rss"
    pages_by_symbol: dict[str, int] | None = None


@dataclass(frozen=True)
class ArcticShiftArchive:
    posts: tuple[RedditPost, ...]
    pages_by_symbol: dict[str, int]
    pages_by_stream: dict[tuple[str, str], int]


@dataclass(frozen=True)
class StocktwitsMessage:
    ticker: str
    message_id: int
    created_at: datetime
    body: str
    username: str
    sentiment: str | None


@dataclass(frozen=True)
class StockTwitsArchive:
    messages_by_symbol: dict[str, tuple[StocktwitsMessage, ...]]
    pages_by_symbol: dict[str, int]
    duplicates_by_symbol: dict[str, int]
    date_range_by_symbol: dict[str, tuple[date, date]]


@dataclass(frozen=True)
class StocktwitsBuildResult(ToolOutputBuildResult):
    messages_by_symbol: dict[str, int]
    pages_by_symbol: dict[str, int]
    duplicates_by_symbol: dict[str, int]


@dataclass(frozen=True)
class DatasetBuildResult:
    price_result: PriceBuildResult
    stock_data_result: ToolOutputBuildResult
    indicators_result: ToolOutputBuildResult
    news_result: ToolOutputBuildResult
    global_news_result: ToolOutputBuildResult
    reddit_result: RedditBuildResult
    stocktwits_result: StocktwitsBuildResult
    fundamentals_result: ToolOutputBuildResult
    balance_sheet_result: ToolOutputBuildResult
    cashflow_result: ToolOutputBuildResult
    income_statement_result: ToolOutputBuildResult


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the prepared TradingAgents evaluation dataset."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Resolve settings and run pre-build checks without writing the DuckDB dataset.",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Optional ticker subset. Defaults to settings.evaluation.tickers.",
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        help="Optional trading-day limit for smoke dataset builds.",
    )
    parser.add_argument(
        "--reddit-delay",
        type=float,
        help=(
            "Seconds to sleep between Reddit RSS requests. Plan B defaults to "
            "at least 10 seconds to avoid unauthenticated Reddit rate limits."
        ),
    )
    parser.add_argument(
        "--reddit-limit-per-sub",
        type=int,
        help="Replay payload post limit per subreddit. Raw fetched posts are still stored.",
    )
    return parser.parse_args(argv)


def options_from_settings(
    args: argparse.Namespace, *, plan_b_defaults: bool = False
) -> BuildDatasetOptions:
    settings = get_settings()
    evaluation = settings.evaluation
    tickers = tuple(ticker.upper() for ticker in (args.tickers or evaluation.tickers))
    dataset_path = PLAN_B_DATASET_PATH if plan_b_defaults else evaluation.dataset_path
    start_date = PLAN_B_START_DATE if plan_b_defaults else evaluation.start_date
    end_date = PLAN_B_END_DATE if plan_b_defaults else evaluation.end_date
    buffer_start_date = (
        PLAN_B_BUFFER_START_DATE if plan_b_defaults else evaluation.buffer_start_date
    )
    return BuildDatasetOptions(
        dataset_path=dataset_path,
        tickers=tickers,
        benchmark=evaluation.benchmark.upper(),
        start_date=start_date,
        end_date=end_date,
        buffer_start_date=buffer_start_date,
        price_tail_days=evaluation.price_tail_days,
        lookback_days=settings.analyst_stage.lookback_days,
        weight_over=evaluation.weight_over,
        weight_under=evaluation.weight_under,
        limit_days=args.limit_days,
        verify_only=bool(args.verify_only),
        news_limit=settings.news.ticker_limit * 2,
        global_news_limit=settings.news.global_limit * 2,
        global_news_lookback_days=settings.news.global_lookback_days,
        reddit_limit_per_sub=(
            settings.sentiment.reddit_limit_per_sub
            if args.reddit_limit_per_sub is None
            else max(args.reddit_limit_per_sub, 0)
        ),
        reddit_request_delay_seconds=(
            max(settings.sentiment.reddit_inter_request_delay, 10.0)
            if args.reddit_delay is None and plan_b_defaults
            else (
                settings.sentiment.reddit_inter_request_delay
                if args.reddit_delay is None
                else max(args.reddit_delay, 0.0)
            )
        ),
        use_arctic_shift_reddit=not plan_b_defaults,
    )


def render_options(options: BuildDatasetOptions) -> str:
    limit_days = "all" if options.limit_days is None else str(options.limit_days)
    return "\n".join(
        [
            "Evaluation dataset settings",
            f"dataset_path: {options.dataset_path}",
            f"tickers: {', '.join(options.tickers)}",
            f"benchmark: {options.benchmark}",
            f"window: {options.start_date}..{options.end_date}",
            f"buffer_start_date: {options.buffer_start_date}",
            f"price_tail_days: {options.price_tail_days}",
            f"lookback_days: {options.lookback_days}",
            f"weight_over: {options.weight_over}",
            f"weight_under: {options.weight_under}",
            f"limit_days: {limit_days}",
            f"news_limit: {options.news_limit}",
            f"global_news_limit: {options.global_news_limit}",
            f"global_news_lookback_days: {options.global_news_lookback_days}",
            f"reddit_limit_per_sub: {options.reddit_limit_per_sub}",
            f"reddit_request_delay_seconds: {options.reddit_request_delay_seconds}",
        ]
    )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _exclusive_tail_end_date(end_date: str, price_tail_days: int) -> str:
    """Return the yfinance-exclusive end date including the configured tail."""
    return (_parse_date(end_date) + timedelta(days=price_tail_days + 1)).isoformat()


def _symbols_for_prices(options: BuildDatasetOptions) -> tuple[str, ...]:
    seen: set[str] = set()
    symbols: list[str] = []
    for symbol in (*options.tickers, options.benchmark):
        normalized = symbol.upper().strip()
        if normalized and normalized not in seen:
            symbols.append(normalized)
            seen.add(normalized)
    return tuple(symbols)


def _download_close_rows(
    symbol: str, start_date: str, end_date: str
) -> list[tuple[str, float]]:
    try:
        history = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch price history for {symbol} from {start_date} to {end_date}: {exc}"
        ) from exc

    if history is None or history.empty:
        raise RuntimeError(
            f"No price history returned for {symbol} from {start_date} to {end_date}."
        )

    prices = _normalise_price_history(history, symbol)
    if prices.empty or "close" not in prices.columns:
        raise RuntimeError(
            f"Price history for {symbol} has no close column from {start_date} to {end_date}."
        )

    rows: list[tuple[str, float]] = []
    for _, row in prices.iterrows():
        close = row["close"]
        if pd.isna(close):
            continue
        try:
            rows.append((str(row["date"]), float(close)))
        except (TypeError, ValueError):
            continue

    if not rows:
        raise RuntimeError(
            f"Price history for {symbol} has no usable close rows from {start_date} to {end_date}."
        )
    return rows


def build_price_table(options: BuildDatasetOptions, dataset: EvalDataset) -> PriceBuildResult:
    """Write buffered close prices and derive the benchmark trading calendar."""
    symbols = _symbols_for_prices(options)
    fetch_start_date = options.buffer_start_date
    fetch_end_date = _exclusive_tail_end_date(options.end_date, options.price_tail_days)
    rows_by_symbol: dict[str, int] = {}

    for symbol in symbols:
        rows = _download_close_rows(symbol, fetch_start_date, fetch_end_date)
        dataset.put_prices(symbol, rows)
        rows_by_symbol[symbol] = len(rows)

    transaction_days = dataset.transaction_days(
        benchmark=options.benchmark,
        start_date=options.start_date,
        end_date=options.end_date,
    )
    if options.limit_days is not None:
        transaction_days = transaction_days[: options.limit_days]
    if not transaction_days:
        raise RuntimeError(
            f"No benchmark transaction days for {options.benchmark} in "
            f"{options.start_date}..{options.end_date}."
        )

    return PriceBuildResult(
        symbols=symbols,
        rows_by_symbol=rows_by_symbol,
        transaction_days=tuple(transaction_days),
        fetch_start_date=fetch_start_date,
        fetch_end_date=fetch_end_date,
    )


def _lookback_start_date(as_of_date: str, lookback_days: int) -> str:
    return (_parse_date(as_of_date) - timedelta(days=lookback_days)).isoformat()


def build_stock_data_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_stock_data`` payloads for each symbol and day."""
    symbols = _symbols_for_prices(options)
    payloads_written = 0

    for symbol in symbols:
        for as_of_date in transaction_days:
            start_date = _lookback_start_date(as_of_date, options.lookback_days)
            payload = get_stock_data_text(symbol, start_date, as_of_date)
            dataset.put_tool_output("get_stock_data", symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name="get_stock_data",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
    )


def _symbols_for_indicator_outputs(options: BuildDatasetOptions) -> tuple[str, ...]:
    """Return evaluated tickers that need replayable indicator payloads."""
    return tuple(
        dict.fromkeys(ticker.upper().strip() for ticker in options.tickers if ticker)
    )


def indicator_names_for_dataset() -> tuple[str, ...]:
    """Return the complete allowed indicator set in deterministic order."""
    return tuple(sorted(ALLOWED_INDICATORS))


def build_indicator_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_indicators`` payloads for each ticker and day."""
    symbols = _symbols_for_indicator_outputs(options)
    indicators = indicator_names_for_dataset()
    if not transaction_days:
        return ToolOutputBuildResult(
            tool_name="get_indicators",
            symbols=symbols,
            payloads_written=0,
            transaction_days=(),
            lookback_days=options.lookback_days,
        )

    earliest_display_start = _lookback_start_date(
        min(transaction_days), options.lookback_days
    )
    latest_end_date = max(transaction_days)
    payload_rows: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        try:
            history = download_indicator_history(
                symbol,
                earliest_display_start,
                latest_end_date,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not download indicator history for {symbol}: {exc}"
            ) from exc
        _validate_indicator_warmup(symbol, history, earliest_display_start)

        for as_of_date in transaction_days:
            start_date = _lookback_start_date(as_of_date, options.lookback_days)
            payload = render_indicators_text(
                symbol,
                start_date,
                as_of_date,
                indicators,
                history,
            )
            if not payload.startswith("Technical indicators for "):
                raise RuntimeError(
                    f"Could not render indicators for {symbol} on {as_of_date}: {payload}"
                )
            payload_rows.append(("get_indicators", symbol, as_of_date, payload))

    dataset.put_tool_outputs(payload_rows)

    return ToolOutputBuildResult(
        tool_name="get_indicators",
        symbols=symbols,
        payloads_written=len(payload_rows),
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
    )


def _validate_indicator_warmup(
    symbol: str,
    history: pd.DataFrame,
    earliest_display_start: str,
) -> None:
    if history is None or history.empty:
        raise RuntimeError(f"Indicator history for {symbol} is empty.")
    prices = _normalise_price_history(history, symbol)
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(prices.columns))
    if missing:
        raise RuntimeError(
            f"Indicator history for {symbol} is missing columns: {', '.join(missing)}."
        )
    display_rows = prices[prices["date"] >= earliest_display_start]
    if display_rows.empty:
        raise RuntimeError(
            f"Indicator history for {symbol} has no rows on or after "
            f"{earliest_display_start}."
        )
    first_display_date = str(display_rows.iloc[0]["date"])
    warmup_rows = len(prices[prices["date"] <= first_display_date])
    if warmup_rows < INDICATOR_MIN_WARMUP_ROWS:
        raise RuntimeError(
            f"Indicator history for {symbol} has {warmup_rows} rows through "
            f"{first_display_date}; at least {INDICATOR_MIN_WARMUP_ROWS} are required."
        )


def build_news_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_news`` payloads for each ticker and day."""
    symbols = _symbols_for_indicator_outputs(options)
    payloads_written = 0

    for symbol in symbols:
        for as_of_date in transaction_days:
            start_date = _lookback_start_date(as_of_date, options.lookback_days)
            try:
                payload = fetch_news_via_exa(
                    symbol,
                    start_date=start_date,
                    end_date=as_of_date,
                    limit=options.news_limit,
                )
            except Exception as exc:
                payload = f"Error fetching news for {symbol}: {exc}"
            dataset.put_tool_output("get_news", symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name="get_news",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
    )


def build_global_news_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_global_news`` payloads for each ticker and day."""
    symbols = _symbols_for_indicator_outputs(options)
    payloads_written = 0

    for as_of_date in transaction_days:
        try:
            payload = fetch_global_news_via_exa(
                curr_date=as_of_date,
                look_back_days=options.global_news_lookback_days,
                limit=options.global_news_limit,
            )
        except Exception as exc:
            payload = f"Error fetching global news for {as_of_date}: {exc}"
        for symbol in symbols:
            dataset.put_tool_output("get_global_news", symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name="get_global_news",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.global_news_lookback_days,
    )


def fetch_reddit_posts_for_dataset(
    *,
    tickers: Sequence[str],
    subreddits: Sequence[str],
    request_delay_seconds: float,
) -> list[RedditPost]:
    """Fetch the raw Plan B Reddit RSS buffer.

    Alias terms are OR-joined so each ``(ticker, subreddit)`` costs one RSS
    request. The returned list is not globally deduped because the dataset keeps
    ticker-specific relevance when one post matches multiple ticker queries.
    """
    posts: list[RedditPost] = []
    first = True
    for ticker in tickers:
        symbol = ticker.upper().strip()
        aliases = DEFAULT_QUERY_ALIASES.get(symbol, (symbol,))
        query = " OR ".join(alias for alias in aliases if alias) or symbol
        for subreddit in subreddits:
            if not first and request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            first = False
            posts.extend(
                fetch_rss_posts(ticker=symbol, subreddit=subreddit, query=query)
            )
    return posts


def load_arctic_shift_posts(
    raw_dir: Path,
    tickers: Sequence[str],
    *,
    subreddits: Sequence[str] | None = None,
) -> ArcticShiftArchive:
    """Load and validate retained Arctic Shift response pages without network I/O."""
    symbols = tuple(dict.fromkeys(ticker.upper().strip() for ticker in tickers))
    expected_subreddits = tuple(
        get_settings().sentiment.reddit_subreddits
        if subreddits is None
        else subreddits
    )
    if not raw_dir.is_dir():
        raise ValueError(f"Arctic Shift archive directory not found: {raw_dir}")

    posts_by_key: dict[tuple[str, str], RedditPost] = {}
    pages_by_symbol = {symbol: 0 for symbol in symbols}
    pages_by_stream = {
        (symbol, subreddit): 0
        for symbol in symbols
        for subreddit in expected_subreddits
    }

    for symbol in symbols:
        for path in sorted(raw_dir.glob(f"{symbol}-*.json")):
            suffix = path.stem[len(symbol) + 1 :]
            try:
                subreddit, sequence = suffix.rsplit("-", 1)
            except ValueError as exc:
                raise ValueError(f"Malformed Arctic Shift filename: {path}") from exc
            if subreddit not in expected_subreddits or not sequence.isdigit():
                raise ValueError(f"Malformed Arctic Shift filename: {path}")

            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Malformed Arctic Shift JSON page {path}: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError(
                    f"Malformed Arctic Shift page {path}: expected a top-level data list"
                )

            pages_by_symbol[symbol] += 1
            pages_by_stream[(symbol, subreddit)] += 1
            for index, raw_post in enumerate(payload["data"]):
                post = _arctic_shift_post_from_raw(
                    symbol, subreddit, raw_post, path=path, index=index
                )
                key = (symbol, post.source_post_id or "")
                previous = posts_by_key.get(key)
                if previous is not None and previous != post:
                    raise ValueError(
                        f"Conflicting duplicate Reddit post {post.source_post_id!r} "
                        f"in Arctic Shift archive for {symbol}"
                    )
                posts_by_key[key] = post

    missing_streams = [
        f"{symbol}/{subreddit}"
        for (symbol, subreddit), count in pages_by_stream.items()
        if count == 0
    ]
    if missing_streams:
        raise ValueError(
            "Arctic Shift archive is missing ticker/subreddit pages: "
            + ", ".join(missing_streams)
        )

    posts = tuple(
        sorted(
            posts_by_key.values(),
            key=lambda post: (post.ticker, post.published_at, post.source_post_id or ""),
        )
    )
    return ArcticShiftArchive(
        posts=posts,
        pages_by_symbol=pages_by_symbol,
        pages_by_stream=pages_by_stream,
    )


def validate_arctic_shift_coverage(
    archive: ArcticShiftArchive,
    tickers: Sequence[str],
    trade_dates: Sequence[str],
    *,
    lookback_days: int,
) -> None:
    """Require each ticker's archive to span the full replay lookback window."""
    if not trade_dates:
        raise ValueError("Cannot validate Arctic Shift coverage without trade dates")
    first_trade_date = min(_parse_date(value) for value in trade_dates)
    last_trade_date = max(_parse_date(value) for value in trade_dates)
    required_start = first_trade_date - timedelta(days=lookback_days)

    failures = []
    for ticker in dict.fromkeys(value.upper().strip() for value in tickers):
        dates = sorted(
            post.published_date
            for post in archive.posts
            if post.ticker == ticker
            and post.published_date <= last_trade_date + timedelta(days=1)
        )
        if not dates:
            failures.append(f"{ticker}: no posts")
            continue
        if dates[0] > required_start or dates[-1] < last_trade_date:
            failures.append(
                f"{ticker}: archive spans {dates[0]}..{dates[-1]}, required "
                f"{required_start}..{last_trade_date}"
            )
    if failures:
        raise ValueError(
            "Insufficient Arctic Shift archive coverage: " + "; ".join(failures)
        )


def build_reddit_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> RedditBuildResult:
    """Record raw Reddit posts and replayable ``fetch_reddit_posts`` payloads."""
    settings = get_settings()
    symbols = _symbols_for_indicator_outputs(options)
    subreddits = tuple(settings.sentiment.reddit_subreddits)
    archive: ArcticShiftArchive | None = None
    if options.use_arctic_shift_reddit:
        archive = load_arctic_shift_posts(
            ARCTIC_SHIFT_RAW_DIR, symbols, subreddits=subreddits
        )
        validate_arctic_shift_coverage(
            archive,
            symbols,
            transaction_days,
            lookback_days=options.lookback_days,
        )
        posts = list(archive.posts)
    else:
        posts = fetch_reddit_posts_for_dataset(
            tickers=symbols,
            subreddits=subreddits,
            request_delay_seconds=options.reddit_request_delay_seconds,
        )
    dataset.put_reddit_posts([_reddit_post_row(post) for post in posts])

    payload_rows: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        symbol_posts = [post for post in posts if post.ticker == symbol]
        for as_of_date in transaction_days:
            payload = render_reddit_payload(
                symbol,
                as_of_date,
                symbol_posts,
                subreddits=subreddits,
                lookback_days=options.lookback_days,
                limit_per_sub=options.reddit_limit_per_sub,
            )
            payload_rows.append(("fetch_reddit_posts", symbol, as_of_date, payload))
    dataset.put_tool_outputs(payload_rows)

    return RedditBuildResult(
        tool_name="fetch_reddit_posts",
        symbols=symbols,
        subreddits=subreddits,
        posts_written=len(posts),
        payloads_written=len(payload_rows),
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
        payload_limit_per_sub=options.reddit_limit_per_sub,
        request_delay_seconds=options.reddit_request_delay_seconds,
        source="arctic-shift" if archive else "reddit-rss",
        pages_by_symbol=archive.pages_by_symbol if archive else None,
    )


def load_stocktwits_messages(
    ticker: str, raw_dir: Path = STOCKTWITS_RAW_DIR
) -> list[StocktwitsMessage]:
    """Load one ticker through the strict offline archive parser."""
    symbol = ticker.upper().strip()
    archive = load_stocktwits_archive(raw_dir, (symbol,))
    return list(archive.messages_by_symbol[symbol])


def load_stocktwits_archive(
    raw_dir: Path,
    tickers: Sequence[str],
    *,
    retain_start_date: date | None = None,
    retain_end_date: date | None = None,
) -> StockTwitsArchive:
    """Validate StockTwits pagination pages and retain deduplicated messages."""
    symbols = tuple(dict.fromkeys(ticker.upper().strip() for ticker in tickers))
    if not raw_dir.is_dir():
        raise ValueError(f"StockTwits archive directory not found: {raw_dir}")

    messages_by_symbol: dict[str, tuple[StocktwitsMessage, ...]] = {}
    pages_by_symbol: dict[str, int] = {}
    duplicates_by_symbol: dict[str, int] = {}
    date_range_by_symbol: dict[str, tuple[date, date]] = {}

    for symbol in symbols:
        paths_by_sequence: dict[int, Path] = {}
        for path in raw_dir.glob(f"{symbol}-*.json"):
            sequence_text = path.stem[len(symbol) + 1 :]
            if not sequence_text.isdigit() or int(sequence_text) < 1:
                raise ValueError(f"Malformed StockTwits archive filename: {path}")
            sequence = int(sequence_text)
            if sequence in paths_by_sequence:
                raise ValueError(
                    f"Ambiguous StockTwits page sequence {symbol}-{sequence}: "
                    f"{paths_by_sequence[sequence]} and {path}"
                )
            paths_by_sequence[sequence] = path

        if not paths_by_sequence:
            raise ValueError(f"StockTwits archive has no pages for {symbol}")
        sequences = sorted(paths_by_sequence)
        expected_sequences = list(range(1, sequences[-1] + 1))
        if sequences != expected_sequences:
            missing = sorted(set(expected_sequences) - set(sequences))
            raise ValueError(
                f"Non-contiguous StockTwits page sequence for {symbol}; "
                f"missing pages: {missing[:10]}"
            )

        retained_by_id: dict[int, StocktwitsMessage] = {}
        fingerprints_by_id: dict[int, bytes] = {}
        duplicate_count = 0
        oldest: date | None = None
        newest: date | None = None
        previous_cursor_max: int | None = None
        previous_newest_at: datetime | None = None

        for sequence in sequences:
            path = paths_by_sequence[sequence]
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Malformed StockTwits JSON page {path}: {exc}") from exc
            raw_messages, cursor = _validate_stocktwits_page(payload, symbol, path)

            cursor_since = cursor["since"]
            cursor_max = cursor["max"]
            if cursor_since <= cursor_max:
                raise ValueError(
                    f"Invalid StockTwits cursor bounds in {path}: "
                    f"since={cursor_since}, max={cursor_max}"
                )
            if previous_cursor_max is not None and cursor_since >= previous_cursor_max:
                raise ValueError(
                    f"Non-monotonic StockTwits cursor at {path}: since={cursor_since} "
                    f"must be below previous max={previous_cursor_max}"
                )
            previous_cursor_max = cursor_max

            page_messages = [
                _validated_stocktwits_message(symbol, raw, path=path, index=index)
                for index, raw in enumerate(raw_messages)
            ]
            page_messages.sort(
                key=lambda message: (message.created_at, message.message_id),
                reverse=True,
            )
            created_values = [message.created_at for message in page_messages]
            page_newest_at = created_values[0]
            if previous_newest_at is not None and page_newest_at > previous_newest_at:
                raise ValueError(
                    f"Ambiguous StockTwits page chronology at {path}: newest message "
                    f"{page_newest_at.isoformat()} is after previous page's newest "
                    f"{previous_newest_at.isoformat()}"
                )
            previous_newest_at = page_newest_at

            for message in page_messages:
                message_date = message.created_at.date()
                oldest = message_date if oldest is None or message_date < oldest else oldest
                newest = message_date if newest is None or message_date > newest else newest
                fingerprint = _stocktwits_message_fingerprint(message)
                previous_fingerprint = fingerprints_by_id.get(message.message_id)
                if previous_fingerprint is not None:
                    duplicate_count += 1
                    if previous_fingerprint != fingerprint:
                        raise ValueError(
                            f"Conflicting duplicate StockTwits message "
                            f"{message.message_id} in {path}"
                        )
                    continue
                fingerprints_by_id[message.message_id] = fingerprint
                if (
                    (retain_start_date is None or message_date >= retain_start_date)
                    and (retain_end_date is None or message_date <= retain_end_date)
                ):
                    retained_by_id[message.message_id] = message

        if oldest is None or newest is None:
            raise ValueError(f"StockTwits archive pages for {symbol} contain no messages")
        messages_by_symbol[symbol] = tuple(
            sorted(
                retained_by_id.values(),
                key=lambda message: (message.created_at, message.message_id),
                reverse=True,
            )
        )
        pages_by_symbol[symbol] = len(sequences)
        duplicates_by_symbol[symbol] = duplicate_count
        date_range_by_symbol[symbol] = (oldest, newest)

    return StockTwitsArchive(
        messages_by_symbol=messages_by_symbol,
        pages_by_symbol=pages_by_symbol,
        duplicates_by_symbol=duplicates_by_symbol,
        date_range_by_symbol=date_range_by_symbol,
    )


def validate_stocktwits_coverage(
    archive: StockTwitsArchive,
    tickers: Sequence[str],
    trade_dates: Sequence[str],
    *,
    lookback_days: int,
) -> None:
    """Require each archive to span the requested replay and lookback dates."""
    if not trade_dates:
        raise ValueError("Cannot validate StockTwits coverage without trade dates")
    required_start = min(_parse_date(value) for value in trade_dates) - timedelta(
        days=lookback_days
    )
    required_end = max(_parse_date(value) for value in trade_dates)
    failures = []
    for symbol in dict.fromkeys(ticker.upper().strip() for ticker in tickers):
        date_range = archive.date_range_by_symbol.get(symbol)
        if date_range is None:
            failures.append(f"{symbol}: no archive range")
            continue
        oldest, newest = date_range
        if oldest > required_start or newest < required_end:
            failures.append(
                f"{symbol}: archive spans {oldest}..{newest}, required "
                f"{required_start}..{required_end}"
            )
    if failures:
        raise ValueError("Insufficient StockTwits archive coverage: " + "; ".join(failures))


def render_stocktwits_payload(
    ticker: str,
    as_of_date: str,
    messages: Sequence[StocktwitsMessage],
    *,
    lookback_days: int,
    limit: int,
) -> str:
    """Render historical StockTwits messages in the live helper's text format."""
    symbol = ticker.upper().strip()
    end_date = _parse_date(as_of_date)
    start_date = end_date - timedelta(days=lookback_days)
    selected = [
        message
        for message in messages
        if start_date <= message.created_at.date() <= end_date
    ][: max(limit, 0)]
    if not selected:
        return f"No data available for StockTwits messages for {symbol}."

    lines = []
    bullish = bearish = unlabeled = 0
    for message in selected:
        if message.sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif message.sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"

        body = _trim_stocktwits_text(" ".join(message.body.split()), 280)
        lines.append(
            f"[{_format_stocktwits_created_at(message.created_at)} · "
            f"@{message.username} · {tag}] {body}"
        )

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


def build_stocktwits_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
    *,
    raw_dir: Path = STOCKTWITS_RAW_DIR,
) -> StocktwitsBuildResult:
    """Record replayable ``fetch_stocktwits_messages`` payloads from raw JSON files."""
    settings = get_settings()
    symbols = _symbols_for_indicator_outputs(options)
    payloads_written = 0
    if not transaction_days:
        raise ValueError("Cannot build StockTwits outputs without transaction days")
    retain_start_date = min(_parse_date(value) for value in transaction_days) - timedelta(
        days=options.lookback_days
    )
    retain_end_date = max(_parse_date(value) for value in transaction_days)
    archive = load_stocktwits_archive(
        raw_dir,
        symbols,
        retain_start_date=retain_start_date,
        retain_end_date=retain_end_date,
    )
    validate_stocktwits_coverage(
        archive,
        symbols,
        transaction_days,
        lookback_days=options.lookback_days,
    )

    for symbol in symbols:
        messages = archive.messages_by_symbol[symbol]
        for as_of_date in transaction_days:
            payload = render_stocktwits_payload(
                symbol,
                as_of_date,
                messages,
                lookback_days=options.lookback_days,
                limit=settings.sentiment.stocktwits_limit,
            )
            dataset.put_tool_output(
                "fetch_stocktwits_messages", symbol, as_of_date, payload
            )
            payloads_written += 1

    return StocktwitsBuildResult(
        tool_name="fetch_stocktwits_messages",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
        messages_by_symbol={
            symbol: len(archive.messages_by_symbol[symbol]) for symbol in symbols
        },
        pages_by_symbol=archive.pages_by_symbol,
        duplicates_by_symbol=archive.duplicates_by_symbol,
    )


def build_snapshot_tool_outputs(
    *,
    tool_name: str,
    render_payload: Callable[[str], str],
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable snapshot payloads for each ticker and day.

    Several yfinance fundamentals endpoints expose latest available snapshots
    rather than point-in-time daily history. Fetch once per ticker and record
    the same payload for every replay date so evaluation mode and normal mode
    see the same tool text shape.
    """
    symbols = _symbols_for_indicator_outputs(options)
    payloads_written = 0

    for symbol in symbols:
        payload = render_payload(symbol)
        for as_of_date in transaction_days:
            dataset.put_tool_output(tool_name, symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name=tool_name,
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=0,
    )


def build_fundamentals_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record point-in-time SEC fundamentals for each ticker and day."""
    symbols = _symbols_for_indicator_outputs(options)
    if not transaction_days:
        return ToolOutputBuildResult(
            tool_name="get_fundamentals",
            symbols=symbols,
            payloads_written=0,
            transaction_days=(),
            lookback_days=0,
        )

    archive = ensure_sec_archive(symbols, transaction_days)
    payload_rows: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        prices = dataset.close_series(symbol)
        for as_of_date in transaction_days:
            payload = render_point_in_time_fundamentals(
                archive,
                symbol,
                as_of_date,
                prices,
            )
            if not payload.startswith(
                f"Point-in-time fundamentals for {symbol} as of {as_of_date}."
            ):
                raise RuntimeError(
                    f"Could not render SEC fundamentals for {symbol} on {as_of_date}."
                )
            payload_rows.append(
                ("get_fundamentals", symbol, as_of_date, payload)
            )

    dataset.put_tool_outputs(payload_rows)
    return ToolOutputBuildResult(
        tool_name="get_fundamentals",
        symbols=symbols,
        payloads_written=len(payload_rows),
        transaction_days=tuple(transaction_days),
        lookback_days=0,
    )


def build_balance_sheet_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_balance_sheet`` payloads for each ticker and day."""
    return build_snapshot_tool_outputs(
        tool_name="get_balance_sheet",
        render_payload=lambda ticker: get_statement_text(
            ticker, "Balance sheet", "balance_sheet"
        ),
        options=options,
        dataset=dataset,
        transaction_days=transaction_days,
    )


def build_cashflow_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_cashflow`` payloads for each ticker and day."""
    return build_snapshot_tool_outputs(
        tool_name="get_cashflow",
        render_payload=lambda ticker: get_statement_text(
            ticker, "Cash flow statement", "cashflow"
        ),
        options=options,
        dataset=dataset,
        transaction_days=transaction_days,
    )


def build_income_statement_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_income_statement`` payloads for each ticker and day."""
    return build_snapshot_tool_outputs(
        tool_name="get_income_statement",
        render_payload=lambda ticker: get_statement_text(
            ticker, "Income statement", "income_stmt"
        ),
        options=options,
        dataset=dataset,
        transaction_days=transaction_days,
    )


def render_reddit_payload(
    ticker: str,
    as_of_date: str,
    posts: Sequence[RedditPost],
    *,
    subreddits: Sequence[str],
    lookback_days: int,
    limit_per_sub: int,
) -> str:
    """Render the small prompt payload from the full raw Reddit buffer."""
    symbol = ticker.upper().strip()
    end_date = _parse_date(as_of_date)
    start_date = end_date - timedelta(days=lookback_days)
    blocks: list[str] = []
    total_posts = 0
    effective_limit = max(limit_per_sub, 0)

    for subreddit in subreddits:
        matching = sorted(
            (
                post
                for post in posts
                if post.ticker == symbol
                and post.subreddit == subreddit
                and start_date <= post.published_date <= end_date
            ),
            key=lambda post: post.published_at,
            reverse=True,
        )
        selected = matching[:effective_limit]
        total_posts += len(selected)
        if not selected:
            blocks.append(
                f"r/{subreddit}: <no posts found mentioning "
                f"{symbol} in the past 7 days>"
            )
            continue

        has_engagement = all(
            post.score is not None and post.num_comments is not None
            for post in selected
        )
        header = f"r/{subreddit} — {len(selected)} recent posts mentioning {symbol}"
        if not has_engagement:
            header += " (via RSS feed; scores/comments unavailable):"
        else:
            header += ":"
        lines = [header]
        for post in selected:
            body = _trim_text(" ".join(post.body.split()), 240)
            meta = post.published_date.isoformat()
            if post.score is not None and post.num_comments is not None:
                meta += f" · {post.score:>4}↑ · {post.num_comments:>3}c"
            lines.append(
                f" [{meta}] {' '.join(post.title.split())}"
                + (f"\n body excerpt: {body}" if body else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        subreddit_names = ", ".join(f"r/{subreddit}" for subreddit in subreddits)
        return (
            f"<no Reddit posts found mentioning {symbol} across "
            f"{subreddit_names} in the past 7 days>"
        )
    return "\n\n".join(blocks)


def _reddit_post_row(
    post: RedditPost,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str | None,
    int | None,
    int | None,
]:
    return (
        post.ticker,
        post.subreddit,
        post.published_at.isoformat(),
        post.published_date.isoformat(),
        post.url,
        post.title,
        post.body,
        post.source_post_id,
        post.score,
        post.num_comments,
    )


def _arctic_shift_post_from_raw(
    ticker: str,
    expected_subreddit: str,
    raw_post: object,
    *,
    path: Path,
    index: int,
) -> RedditPost:
    location = f"{path} data[{index}]"
    if not isinstance(raw_post, dict):
        raise ValueError(f"Malformed Arctic Shift post at {location}: expected object")

    required = (
        "id",
        "created_utc",
        "subreddit",
        "title",
        "selftext",
        "score",
        "num_comments",
    )
    missing = [key for key in required if key not in raw_post or raw_post[key] is None]
    if missing:
        raise ValueError(
            f"Malformed Arctic Shift post at {location}: missing required fields "
            + ", ".join(missing)
        )

    post_id = raw_post["id"]
    created_utc = raw_post["created_utc"]
    subreddit = raw_post["subreddit"]
    title = raw_post["title"]
    body = raw_post["selftext"]
    score = raw_post["score"]
    num_comments = raw_post["num_comments"]
    if not isinstance(post_id, str) or not post_id.strip():
        raise ValueError(f"Malformed Arctic Shift post at {location}: invalid id")
    if isinstance(created_utc, bool) or not isinstance(created_utc, (int, float)):
        raise ValueError(f"Malformed Arctic Shift post at {location}: invalid created_utc")
    if subreddit != expected_subreddit:
        raise ValueError(
            f"Malformed Arctic Shift post at {location}: subreddit {subreddit!r} "
            f"does not match filename subreddit {expected_subreddit!r}"
        )
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError(f"Malformed Arctic Shift post at {location}: invalid text fields")
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError(f"Malformed Arctic Shift post at {location}: invalid score")
    if isinstance(num_comments, bool) or not isinstance(num_comments, int):
        raise ValueError(f"Malformed Arctic Shift post at {location}: invalid num_comments")

    published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    return RedditPost(
        ticker=ticker,
        subreddit=subreddit,
        title=title,
        published_at=published_at,
        published_date=published_at.date(),
        url=f"https://www.reddit.com/comments/{post_id}/",
        body=body,
        source_post_id=post_id,
        score=score,
        num_comments=num_comments,
    )


def _trim_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 1:
        return value[:max_length]
    return value[:max_length] + "..."


def _validate_stocktwits_page(
    payload: object, symbol: str, path: Path
) -> tuple[list[object], dict[str, object]]:
    if not isinstance(payload, dict):
        raise ValueError(f"Malformed StockTwits page {path}: expected object")
    raw_symbol = payload.get("symbol")
    if not isinstance(raw_symbol, dict) or raw_symbol.get("symbol") != symbol:
        raise ValueError(
            f"Malformed StockTwits page {path}: symbol does not match {symbol}"
        )
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError(
            f"Malformed StockTwits page {path}: expected a non-empty messages list"
        )
    cursor = payload.get("cursor")
    if not isinstance(cursor, dict):
        raise ValueError(f"Malformed StockTwits page {path}: expected cursor object")
    if not isinstance(cursor.get("more"), bool):
        raise ValueError(f"Malformed StockTwits cursor in {path}: invalid more")
    for field_name in ("since", "max"):
        value = cursor.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"Malformed StockTwits cursor in {path}: invalid {field_name}"
            )
    return raw_messages, cursor


def _validated_stocktwits_message(
    ticker: str,
    raw_message: object,
    *,
    path: Path,
    index: int,
) -> StocktwitsMessage:
    location = f"{path} messages[{index}]"
    if not isinstance(raw_message, dict):
        raise ValueError(f"Malformed StockTwits message at {location}: expected object")
    required = ("id", "created_at", "body", "user", "entities")
    missing = [
        key for key in required if key not in raw_message or raw_message[key] is None
    ]
    if missing:
        raise ValueError(
            f"Malformed StockTwits message at {location}: missing required fields "
            + ", ".join(missing)
        )

    message_id = raw_message["id"]
    if isinstance(message_id, bool) or not isinstance(message_id, int):
        raise ValueError(f"Malformed StockTwits message at {location}: invalid id")
    created_at = _parse_stocktwits_datetime(raw_message["created_at"])
    if created_at is None:
        raise ValueError(
            f"Malformed StockTwits message at {location}: invalid created_at"
        )
    body = raw_message["body"]
    if not isinstance(body, str):
        raise ValueError(f"Malformed StockTwits message at {location}: invalid body")
    user = raw_message["user"]
    if not isinstance(user, dict) or not isinstance(user.get("username"), str):
        raise ValueError(f"Malformed StockTwits message at {location}: invalid user")
    entities = raw_message["entities"]
    if not isinstance(entities, dict):
        raise ValueError(f"Malformed StockTwits message at {location}: invalid entities")
    sentiment_obj = entities.get("sentiment")
    sentiment: str | None = None
    if sentiment_obj is not None:
        if not isinstance(sentiment_obj, dict):
            raise ValueError(
                f"Malformed StockTwits message at {location}: invalid sentiment"
            )
        raw_sentiment = sentiment_obj.get("basic")
        if raw_sentiment not in (None, "Bullish", "Bearish"):
            raise ValueError(
                f"Malformed StockTwits message at {location}: invalid sentiment"
            )
        sentiment = raw_sentiment

    return StocktwitsMessage(
        ticker=ticker,
        message_id=message_id,
        created_at=created_at,
        body=body,
        username=user["username"],
        sentiment=sentiment,
    )


def _stocktwits_message_fingerprint(message: StocktwitsMessage) -> bytes:
    normalized = json.dumps(
        (
            message.created_at.isoformat(),
            message.body,
            message.username,
            message.sentiment,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.blake2b(normalized, digest_size=16).digest()


def _parse_stocktwits_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_stocktwits_created_at(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trim_stocktwits_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 1:
        return value[:max_length]
    return value[:max_length] + "…"


def build_dataset(options: BuildDatasetOptions) -> DatasetBuildResult:
    """Build the currently implemented shared dataset pieces."""
    with EvalDataset(options.dataset_path) as dataset:
        price_result = build_price_table(options, dataset)
        stock_data_result = build_stock_data_outputs(
            options, dataset, price_result.transaction_days
        )
        indicators_result = build_indicator_outputs(
            options, dataset, price_result.transaction_days
        )
        news_result = build_news_outputs(options, dataset, price_result.transaction_days)
        global_news_result = build_global_news_outputs(
            options, dataset, price_result.transaction_days
        )
        reddit_result = build_reddit_outputs(
            options, dataset, price_result.transaction_days
        )
        stocktwits_result = build_stocktwits_outputs(
            options, dataset, price_result.transaction_days
        )
        fundamentals_result = build_fundamentals_outputs(
            options, dataset, price_result.transaction_days
        )
        balance_sheet_result = build_balance_sheet_outputs(
            options, dataset, price_result.transaction_days
        )
        cashflow_result = build_cashflow_outputs(
            options, dataset, price_result.transaction_days
        )
        income_statement_result = build_income_statement_outputs(
            options, dataset, price_result.transaction_days
        )
        return DatasetBuildResult(
            price_result=price_result,
            stock_data_result=stock_data_result,
            indicators_result=indicators_result,
            news_result=news_result,
            global_news_result=global_news_result,
            reddit_result=reddit_result,
            stocktwits_result=stocktwits_result,
            fundamentals_result=fundamentals_result,
            balance_sheet_result=balance_sheet_result,
            cashflow_result=cashflow_result,
            income_statement_result=income_statement_result,
        )


def render_price_result(result: PriceBuildResult) -> str:
    lines = [
        "Price table built",
        f"price_window: {result.fetch_start_date}..{result.fetch_end_date} (end exclusive)",
        "price_rows:",
    ]
    for symbol in result.symbols:
        lines.append(f"  {symbol}: {result.rows_by_symbol[symbol]}")
    lines.extend(
        [
            f"transaction_days: {len(result.transaction_days)}",
            f"first_transaction_day: {result.transaction_days[0]}",
            f"last_transaction_day: {result.transaction_days[-1]}",
        ]
    )
    return "\n".join(lines)


def render_tool_output_result(result: ToolOutputBuildResult) -> str:
    first_day = result.transaction_days[0] if result.transaction_days else "n/a"
    last_day = result.transaction_days[-1] if result.transaction_days else "n/a"
    return "\n".join(
        [
            f"{result.tool_name} outputs built",
            f"symbols: {', '.join(result.symbols)}",
            f"payloads_written: {result.payloads_written}",
            f"transaction_days: {len(result.transaction_days)}",
            f"first_transaction_day: {first_day}",
            f"last_transaction_day: {last_day}",
            f"lookback_days: {result.lookback_days}",
        ]
    )


def render_reddit_result(result: RedditBuildResult) -> str:
    first_day = result.transaction_days[0] if result.transaction_days else "n/a"
    last_day = result.transaction_days[-1] if result.transaction_days else "n/a"
    lines = [
        f"{result.tool_name} outputs built",
        f"source: {result.source}",
        f"symbols: {', '.join(result.symbols)}",
        f"subreddits: {', '.join(result.subreddits)}",
        f"posts_written: {result.posts_written}",
        f"payloads_written: {result.payloads_written}",
        f"transaction_days: {len(result.transaction_days)}",
        f"first_transaction_day: {first_day}",
        f"last_transaction_day: {last_day}",
        f"lookback_days: {result.lookback_days}",
        f"payload_limit_per_sub: {result.payload_limit_per_sub}",
        f"request_delay_seconds: {result.request_delay_seconds}",
    ]
    if result.pages_by_symbol:
        lines.append("archive_pages:")
        lines.extend(
            f"  {symbol}: {result.pages_by_symbol[symbol]}" for symbol in result.symbols
        )
    return "\n".join(lines)


def render_stocktwits_result(result: StocktwitsBuildResult) -> str:
    lines = [
        f"{result.tool_name} outputs built",
        "source: stocktwits-archive",
        f"symbols: {', '.join(result.symbols)}",
        f"payloads_written: {result.payloads_written}",
        f"transaction_days: {len(result.transaction_days)}",
        f"lookback_days: {result.lookback_days}",
        "archive:",
    ]
    lines.extend(
        f"  {symbol}: pages={result.pages_by_symbol[symbol]} "
        f"messages={result.messages_by_symbol[symbol]} "
        f"duplicates={result.duplicates_by_symbol[symbol]}"
        for symbol in result.symbols
    )
    return "\n".join(lines)


def render_dataset_result(result: DatasetBuildResult) -> str:
    return "\n".join(
        [
            render_price_result(result.price_result),
            render_tool_output_result(result.stock_data_result),
            render_tool_output_result(result.indicators_result),
            render_tool_output_result(result.news_result),
            render_tool_output_result(result.global_news_result),
            render_reddit_result(result.reddit_result),
            render_stocktwits_result(result.stocktwits_result),
            render_tool_output_result(result.fundamentals_result),
            render_tool_output_result(result.balance_sheet_result),
            render_tool_output_result(result.cashflow_result),
            render_tool_output_result(result.income_statement_result),
        ]
    )


def _run(argv: Sequence[str] | None, *, plan_b_defaults: bool) -> int:
    args = parse_args(argv)
    options = options_from_settings(args, plan_b_defaults=plan_b_defaults)
    print(render_options(options))
    if options.verify_only:
        print("verify-only: dataset writes skipped")
        return 0
    result = build_dataset(options)
    print(render_dataset_result(result))
    return 0


def plan_b_main(argv: Sequence[str] | None = None) -> int:
    return _run(argv, plan_b_defaults=True)


def main(argv: Sequence[str] | None = None) -> int:
    return _run(argv, plan_b_defaults=False)


if __name__ == "__main__":
    raise SystemExit(plan_b_main())
