"""CLI support for building prepared evaluation datasets.

This module owns the shared dataset-building pieces for both the canonical
Plan 07 evaluation and the Plan B evaluation. The two entry points differ only
in their default date window and dataset path; the write paths are shared so the
backtest mechanics remain comparable.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
from trading_agents.tools.fundamentals import get_fundamentals_text
from trading_agents.tools.market_data import (
    ALLOWED_INDICATORS,
    _normalise_price_history,
    get_indicators_text,
    get_stock_data_text,
)


PLAN_B_START_DATE = "2026-01-01"
PLAN_B_END_DATE = "2026-03-31"
PLAN_B_BUFFER_START_DATE = "2025-12-01"
PLAN_B_DATASET_PATH = "data/eval_dataset_2026q1.duckdb"


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


@dataclass(frozen=True)
class DatasetBuildResult:
    price_result: PriceBuildResult
    stock_data_result: ToolOutputBuildResult
    indicators_result: ToolOutputBuildResult
    news_result: ToolOutputBuildResult
    global_news_result: ToolOutputBuildResult
    reddit_result: RedditBuildResult
    fundamentals_result: ToolOutputBuildResult


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
    payloads_written = 0

    for symbol in symbols:
        for as_of_date in transaction_days:
            start_date = _lookback_start_date(as_of_date, options.lookback_days)
            payload = get_indicators_text(symbol, start_date, as_of_date, indicators)
            dataset.put_tool_output("get_indicators", symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name="get_indicators",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
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


def build_reddit_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> RedditBuildResult:
    """Record raw Reddit posts and replayable ``fetch_reddit_posts`` payloads."""
    settings = get_settings()
    symbols = _symbols_for_indicator_outputs(options)
    subreddits = tuple(settings.sentiment.reddit_subreddits)
    posts = fetch_reddit_posts_for_dataset(
        tickers=symbols,
        subreddits=subreddits,
        request_delay_seconds=options.reddit_request_delay_seconds,
    )
    dataset.put_reddit_posts([_reddit_post_row(post) for post in posts])

    payloads_written = 0
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
            dataset.put_tool_output("fetch_reddit_posts", symbol, as_of_date, payload)
            payloads_written += 1

    return RedditBuildResult(
        tool_name="fetch_reddit_posts",
        symbols=symbols,
        subreddits=subreddits,
        posts_written=len(posts),
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=options.lookback_days,
        payload_limit_per_sub=options.reddit_limit_per_sub,
        request_delay_seconds=options.reddit_request_delay_seconds,
    )


def build_fundamentals_outputs(
    options: BuildDatasetOptions,
    dataset: EvalDataset,
    transaction_days: Sequence[str],
) -> ToolOutputBuildResult:
    """Record replayable ``get_fundamentals`` payloads for each ticker and day.

    The live ``get_fundamentals`` tool is a current yfinance ``Ticker.info``
    snapshot rather than a point-in-time historical feed. Fetch once per ticker
    and record the same payload for every replay date so evaluation mode and
    normal mode see the same tool text shape.
    """
    symbols = _symbols_for_indicator_outputs(options)
    payloads_written = 0

    for symbol in symbols:
        payload = get_fundamentals_text(symbol)
        for as_of_date in transaction_days:
            dataset.put_tool_output("get_fundamentals", symbol, as_of_date, payload)
            payloads_written += 1

    return ToolOutputBuildResult(
        tool_name="get_fundamentals",
        symbols=symbols,
        payloads_written=payloads_written,
        transaction_days=tuple(transaction_days),
        lookback_days=0,
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
            blocks.append(f"r/{subreddit}: ")
            continue

        lines = [
            f"r/{subreddit} - {len(selected)} recent posts mentioning {symbol} "
            "(via RSS feed; scores/comments unavailable):"
        ]
        for post in selected:
            body = _trim_text(" ".join(post.body.split()), 240)
            lines.append(
                f" [{post.published_date.isoformat()}] {' '.join(post.title.split())}"
                + (f"\n body excerpt: {body}" if body else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return f"No data available for Reddit posts for {symbol}."
    return "\n\n".join(blocks)


def _reddit_post_row(post: RedditPost) -> tuple[str, str, str, str, str, str, str]:
    return (
        post.ticker,
        post.subreddit,
        post.published_at.isoformat(),
        post.published_date.isoformat(),
        post.url,
        post.title,
        post.body,
    )


def _trim_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 1:
        return value[:max_length]
    return value[:max_length] + "..."


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
        fundamentals_result = build_fundamentals_outputs(
            options, dataset, price_result.transaction_days
        )
        return DatasetBuildResult(
            price_result=price_result,
            stock_data_result=stock_data_result,
            indicators_result=indicators_result,
            news_result=news_result,
            global_news_result=global_news_result,
            reddit_result=reddit_result,
            fundamentals_result=fundamentals_result,
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
    return "\n".join(
        [
            f"{result.tool_name} outputs built",
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
    )


def render_dataset_result(result: DatasetBuildResult) -> str:
    return "\n".join(
        [
            render_price_result(result.price_result),
            render_tool_output_result(result.stock_data_result),
            render_tool_output_result(result.indicators_result),
            render_tool_output_result(result.news_result),
            render_tool_output_result(result.global_news_result),
            render_reddit_result(result.reddit_result),
            render_tool_output_result(result.fundamentals_result),
            "remaining tool-output builders: pending",
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
