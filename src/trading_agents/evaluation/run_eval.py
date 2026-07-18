"""Run the prepared-dataset cumulative-return evaluation."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from trading_agents.config import get_settings
from trading_agents.crews.portfolio_crew.lesson_store import LessonStore
from trading_agents.evaluation.backtest import cumulative_return, simulate_position
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.schemas import PortfolioRating


StageRunner = Callable[[Mapping[str, Any]], dict[str, Any]]
PortfolioStageRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class StageRunners:
    analyst: StageRunner
    research: StageRunner
    trader: StageRunner
    risk: StageRunner
    portfolio: PortfolioStageRunner


@dataclass(frozen=True)
class DecisionRecord:
    date: str
    ticker: str
    rating: str
    close: float


@dataclass(frozen=True)
class TickerEvaluation:
    ticker: str
    cumulative_return: float
    total_profit: float


@dataclass(frozen=True)
class EvaluationResult:
    trading_days: tuple[str, ...]
    decisions: tuple[DecisionRecord, ...]
    ticker_results: tuple[TickerEvaluation, ...]
    markdown_path: Path
    csv_path: Path


def _load_stage_runners() -> StageRunners:
    from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage
    from trading_agents.crews.portfolio_crew.portfolio_crew import run_portfolio_stage
    from trading_agents.crews.research_crew.research_crew import run_research_stage
    from trading_agents.crews.risk_management_crew.risk_management_crew import (
        run_risk_stage,
    )
    from trading_agents.crews.trader_crew.trader_crew import run_trader_stage

    return StageRunners(
        analyst=run_analyst_stage,
        research=run_research_stage,
        trader=run_trader_stage,
        risk=run_risk_stage,
        portfolio=run_portfolio_stage,
    )


def run_evaluation(
    *,
    dataset_path: str | Path,
    tickers: Sequence[str],
    output_dir: str | Path = "output/eval",
    limit_days: int | None = None,
    runners: StageRunners | None = None,
) -> EvaluationResult:
    """Run every selected ticker for every selected transaction day."""
    settings = get_settings()
    evaluation = settings.evaluation
    selected_tickers = _normalize_tickers(tickers)
    if not evaluation.enabled:
        raise RuntimeError("Evaluation mode must be enabled before running evaluation.")
    if limit_days is not None and limit_days < 1:
        raise ValueError("limit_days must be at least 1.")
    if runners is None:
        runners = _load_stage_runners()

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with EvalDataset(dataset_path, read_only=True) as dataset:
        trading_days = dataset.transaction_days(
            benchmark=evaluation.benchmark,
            start_date=evaluation.start_date,
            end_date=evaluation.end_date,
        )
        if limit_days is not None:
            trading_days = trading_days[:limit_days]
        if not trading_days:
            raise ValueError(
                "Evaluation dataset has no benchmark trading days in the configured window."
            )

        close_series = {
            symbol: dataset.close_series(symbol)
            for symbol in (*selected_tickers, evaluation.benchmark.upper())
        }
        _validate_price_coverage(selected_tickers, trading_days, close_series)

        def fetch_series(symbol: str, _trade_date: str) -> list[tuple[str, float]]:
            normalized = symbol.strip().upper()
            try:
                return close_series[normalized]
            except KeyError as exc:
                raise KeyError(
                    f"No recorded evaluation price series for {normalized}."
                ) from exc

        decisions: list[DecisionRecord] = []
        with TemporaryDirectory(prefix="lessons-", dir=output_path) as lessons_dir:
            lesson_store = LessonStore(lessons_dir)
            for trade_date in trading_days:
                for ticker in selected_tickers:
                    print(f"Evaluating {ticker} on {trade_date}")
                    rating = _run_decision_pipeline(
                        runners,
                        ticker=ticker,
                        trade_date=trade_date,
                        lesson_store=lesson_store,
                        fetch_series=fetch_series,
                    )
                    close = dict(close_series[ticker])[trade_date]
                    decisions.append(
                        DecisionRecord(
                            date=trade_date,
                            ticker=ticker,
                            rating=rating,
                            close=close,
                        )
                    )

    ticker_results = _score_tickers(
        selected_tickers,
        decisions,
        weight_over=evaluation.weight_over,
        weight_under=evaluation.weight_under,
    )
    markdown_path = output_path / "evaluation_report.md"
    csv_path = output_path / "evaluation_results.csv"
    _write_markdown_report(
        markdown_path,
        trading_days=trading_days,
        decisions=decisions,
        ticker_results=ticker_results,
        start_date=evaluation.start_date,
        end_date=evaluation.end_date,
    )
    _write_csv_report(csv_path, decisions, ticker_results)

    return EvaluationResult(
        trading_days=tuple(trading_days),
        decisions=tuple(decisions),
        ticker_results=tuple(ticker_results),
        markdown_path=markdown_path,
        csv_path=csv_path,
    )


def _run_decision_pipeline(
    runners: StageRunners,
    *,
    ticker: str,
    trade_date: str,
    lesson_store: LessonStore,
    fetch_series: Callable[[str, str], Sequence[tuple[str, float]]],
) -> str:
    reports = runners.analyst({"ticker": ticker, "trade_date": trade_date})
    research = runners.research(
        {"ticker": ticker, "trade_date": trade_date, **reports}
    )
    trader = runners.trader(
        {
            "ticker": ticker,
            "trade_date": trade_date,
            "investment_plan": research["investment_plan"],
        }
    )
    trader_plan = _as_dict(trader["trader_plan"])
    risk = runners.risk(
        {
            "ticker": ticker,
            "trade_date": trade_date,
            **reports,
            "trader_plan": trader["trader_plan"],
        }
    )
    portfolio = runners.portfolio(
        {
            "ticker": ticker,
            "trade_date": trade_date,
            "investment_plan": research["investment_plan"],
            "trader_plan": trader_plan,
            "risk_debate_history": risk["risk_debate_history"],
        },
        store=lesson_store,
        fetch_series=fetch_series,
    )
    raw_rating = portfolio["final_trade_decision"]["rating"]
    if isinstance(raw_rating, PortfolioRating):
        return raw_rating.value
    return PortfolioRating(str(raw_rating)).value


def _score_tickers(
    tickers: Sequence[str],
    decisions: Sequence[DecisionRecord],
    *,
    weight_over: float,
    weight_under: float,
) -> list[TickerEvaluation]:
    results: list[TickerEvaluation] = []
    for ticker in tickers:
        ticker_decisions = [record for record in decisions if record.ticker == ticker]
        closes = {record.date: record.close for record in ticker_decisions}
        backtest = simulate_position(
            [(record.date, record.rating) for record in ticker_decisions],
            closes,
            weight_over,
            weight_under,
        )
        results.append(
            TickerEvaluation(
                ticker=ticker,
                cumulative_return=cumulative_return(backtest, weight_over),
                total_profit=backtest.total_profit,
            )
        )
    return results


def _validate_price_coverage(
    tickers: Sequence[str],
    trading_days: Sequence[str],
    close_series: Mapping[str, Sequence[tuple[str, float]]],
) -> None:
    for ticker in tickers:
        available_dates = {date for date, _close in close_series[ticker]}
        missing = [date for date in trading_days if date not in available_dates]
        if missing:
            raise ValueError(
                f"Evaluation dataset is missing {ticker} closes for: "
                + ", ".join(missing)
            )


def _normalize_tickers(tickers: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers))
    if not normalized or any(not ticker for ticker in normalized):
        raise ValueError("At least one non-empty ticker is required.")
    return normalized


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected a structured trader plan, got {type(value).__name__}.")


def _write_markdown_report(
    path: Path,
    *,
    trading_days: Sequence[str],
    decisions: Sequence[DecisionRecord],
    ticker_results: Sequence[TickerEvaluation],
    start_date: str,
    end_date: str,
) -> None:
    lines = [
        "# TradingAgents Evaluation",
        "",
        "> This evaluation invokes language models and can be expensive to run.",
        "",
        f"Period: {start_date}..{end_date} ({len(trading_days)} trading days)",
        "",
        "## Summary",
        "",
        "| Ticker | CR | Total profit |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(
        f"| {result.ticker} | {result.cumulative_return:+.2f}% | "
        f"{result.total_profit:+.4f} |"
        for result in ticker_results
    )
    lines.extend(
        [
            "",
            "## Decisions",
            "",
            "| Date | Ticker | Rating | Close |",
            "| --- | --- | --- | ---: |",
        ]
    )
    lines.extend(
        f"| {record.date} | {record.ticker} | {record.rating} | "
        f"{record.close:.4f} |"
        for record in decisions
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv_report(
    path: Path,
    decisions: Sequence[DecisionRecord],
    ticker_results: Sequence[TickerEvaluation],
) -> None:
    returns = {
        result.ticker: result.cumulative_return for result in ticker_results
    }
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("date", "ticker", "rating", "close", "cumulative_return_pct"))
        for record in decisions:
            writer.writerow(
                (
                    record.date,
                    record.ticker,
                    record.rating,
                    f"{record.close:.10g}",
                    f"{returns[record.ticker]:.10g}",
                )
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the prepared TradingAgents cumulative-return evaluation."
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Optional ticker subset. Defaults to settings.evaluation.tickers.",
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        help="Optional positive trading-day limit for a smoke evaluation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.limit_days is not None and args.limit_days < 1:
        raise SystemExit("--limit-days must be at least 1")

    os.environ["TRADING_AGENTS_EVALUATION__ENABLED"] = "true"
    get_settings.cache_clear()
    evaluation = get_settings().evaluation
    result = run_evaluation(
        dataset_path=evaluation.dataset_path,
        tickers=args.tickers or evaluation.tickers,
        limit_days=args.limit_days,
    )

    print(
        f"TradingAgents evaluation - {evaluation.start_date}..{evaluation.end_date} "
        f"({len(result.trading_days)} trading days)"
    )
    for ticker_result in result.ticker_results:
        print(
            f"{ticker_result.ticker:<6} CR = "
            f"{ticker_result.cumulative_return:+.2f}%"
        )
    print(f"Reports: {result.markdown_path} and {result.csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
