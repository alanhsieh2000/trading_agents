"""CLI support for building prepared evaluation datasets.

This module owns the shared dataset-building pieces for both the canonical
Plan 07 evaluation and the Plan B evaluation. The two entry points differ only
in their default date window and dataset path; the write paths are shared so the
backtest mechanics remain comparable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Sequence

import pandas as pd
import yfinance as yf

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.tools.market_data import _normalise_price_history


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
    weight_over: float
    weight_under: float
    limit_days: int | None
    verify_only: bool


@dataclass(frozen=True)
class PriceBuildResult:
    symbols: tuple[str, ...]
    rows_by_symbol: dict[str, int]
    transaction_days: tuple[str, ...]
    fetch_start_date: str
    fetch_end_date: str


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
    return parser.parse_args(argv)


def options_from_settings(
    args: argparse.Namespace, *, plan_b_defaults: bool = False
) -> BuildDatasetOptions:
    evaluation = get_settings().evaluation
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
        weight_over=evaluation.weight_over,
        weight_under=evaluation.weight_under,
        limit_days=args.limit_days,
        verify_only=bool(args.verify_only),
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
            f"weight_over: {options.weight_over}",
            f"weight_under: {options.weight_under}",
            f"limit_days: {limit_days}",
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


def _download_close_rows(symbol: str, start_date: str, end_date: str) -> list[tuple[str, float]]:
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


def build_dataset(options: BuildDatasetOptions) -> PriceBuildResult:
    """Build the currently implemented shared dataset pieces."""
    with EvalDataset(options.dataset_path) as dataset:
        return build_price_table(options, dataset)


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
            "tool-output builders: pending",
        ]
    )
    return "\n".join(lines)


def _run(argv: Sequence[str] | None, *, plan_b_defaults: bool) -> int:
    args = parse_args(argv)
    options = options_from_settings(args, plan_b_defaults=plan_b_defaults)
    print(render_options(options))
    if options.verify_only:
        print("verify-only: dataset writes skipped")
        return 0
    result = build_dataset(options)
    print(render_price_result(result))
    return 0


def plan_b_main(argv: Sequence[str] | None = None) -> int:
    return _run(argv, plan_b_defaults=True)


def main(argv: Sequence[str] | None = None) -> int:
    return _run(argv, plan_b_defaults=False)


if __name__ == "__main__":
    raise SystemExit(plan_b_main())
