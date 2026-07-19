"""Run the prepared-dataset cumulative-return evaluation."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from trading_agents.config import get_settings
from trading_agents.crews.portfolio_crew.lesson_store import LessonStore
from trading_agents.evaluation.backtest import cumulative_return, simulate_position
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation.quota import (
    DailyQuotaReached,
    EvaluationQuotaLimiter,
    evaluation_quota_hook,
)
from trading_agents.schemas import LessonBook, PortfolioRating


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
    llm_requests: int = 0
    sessions: int = 1


class EvaluationPaused(RuntimeError):
    """Expected pause after the safe daily request budget is exhausted."""

    def __init__(
        self,
        *,
        completed: int,
        total: int,
        used: int,
        budget: int,
        next_reset: datetime,
    ) -> None:
        self.completed = completed
        self.total = total
        self.used = used
        self.budget = budget
        self.next_reset = next_reset
        super().__init__(
            f"Evaluation paused after {completed}/{total} decisions; "
            f"daily requests {used}/{budget}."
        )


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


def _evaluation_fingerprint(
    *,
    dataset_path: str | Path,
    tickers: Sequence[str],
    trading_days: Sequence[str],
) -> str:
    settings = get_settings()
    dataset = Path(dataset_path)
    digest = hashlib.sha256()
    with dataset.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    payload = {
        "dataset_sha256": digest.hexdigest(),
        "tickers": list(tickers),
        "trading_days": list(trading_days),
        "quick_llm": settings.llm.quick_llm,
        "deep_llm": settings.llm.deep_llm,
        "research_max_rounds": settings.research_stage.max_rounds,
        "risk_max_rounds": settings.risk_stage.max_rounds,
        "max_lessons": settings.portfolio_stage.max_lessons,
        "max_holding_days": settings.portfolio_stage.max_holding_days,
        "benchmark": settings.evaluation.benchmark,
        "weight_over": settings.evaluation.weight_over,
        "weight_under": settings.evaluation.weight_under,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_or_create_checkpoint(
    path: Path,
    *,
    fingerprint: str,
    tickers: Sequence[str],
    trading_days: Sequence[str],
    models: Sequence[str],
    limiter: EvaluationQuotaLimiter,
    restart: bool,
) -> dict[str, Any]:
    if restart and path.exists():
        path.unlink()
    if path.exists():
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        if checkpoint.get("version") != 1:
            raise ValueError(
                f"Unsupported evaluation checkpoint {path}; use --restart."
            )
        if checkpoint.get("fingerprint") != fingerprint:
            raise ValueError(
                f"Evaluation checkpoint {path} does not match this run; "
                "use --restart to discard progress."
            )
        return checkpoint

    checkpoint = {
        "version": 1,
        "fingerprint": fingerprint,
        "status": "in_progress",
        "tickers": list(tickers),
        "trading_days": list(trading_days),
        "decisions": [],
        "lessons": {},
        "sessions": 0,
        "llm_requests": 0,
        "quota_start_counts": {
            model: limiter.lifetime_count(model) for model in models
        },
    }
    _write_checkpoint(path, checkpoint)
    return checkpoint


def _write_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(checkpoint), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _decision_payload(record: DecisionRecord) -> dict[str, Any]:
    return {
        "date": record.date,
        "ticker": record.ticker,
        "rating": record.rating,
        "close": record.close,
    }


def _validate_checkpoint_prefix(
    decisions: Sequence[DecisionRecord], expected_pairs: Sequence[tuple[str, str]]
) -> None:
    observed = [(record.date, record.ticker) for record in decisions]
    if observed != list(expected_pairs[: len(observed)]):
        raise ValueError(
            "Evaluation checkpoint decisions are not a chronological prefix; "
            "use --restart to discard progress."
        )


def _restore_lessons(store: LessonStore, lessons: Mapping[str, Any]) -> None:
    for ticker, records in lessons.items():
        store.save(str(ticker), LessonBook.model_validate({"lessons": records}))


def _snapshot_lessons(
    store: LessonStore, tickers: Sequence[str]
) -> dict[str, list[dict[str, Any]]]:
    return {
        ticker: [record.model_dump(mode="json") for record in store.load(ticker).lessons]
        for ticker in tickers
    }


def _point_in_time_fetcher(
    close_series: Mapping[str, Sequence[tuple[str, float]]], as_of_date: str
) -> Callable[[str, str], list[tuple[str, float]]]:
    def fetch(symbol: str, _trade_date: str) -> list[tuple[str, float]]:
        normalized = symbol.strip().upper()
        try:
            series = close_series[normalized]
        except KeyError as exc:
            raise KeyError(
                f"No recorded evaluation price series for {normalized}."
            ) from exc
        return [(date, close) for date, close in series if date <= as_of_date]

    return fetch


def _request_delta(
    checkpoint: Mapping[str, Any], limiter: EvaluationQuotaLimiter
) -> int:
    starts = checkpoint.get("quota_start_counts", {})
    return sum(
        max(0, limiter.lifetime_count(str(model)) - int(start))
        for model, start in starts.items()
    )


def _paused(
    limiter: EvaluationQuotaLimiter,
    *,
    model: str,
    completed: int,
    total: int,
    budget: int,
) -> EvaluationPaused:
    return EvaluationPaused(
        completed=completed,
        total=total,
        used=budget - limiter.remaining(model),
        budget=budget,
        next_reset=limiter.next_reset(),
    )


def _contains_exception(exc: BaseException, expected: type[BaseException]) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, expected):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def run_evaluation(
    *,
    dataset_path: str | Path,
    tickers: Sequence[str],
    output_dir: str | Path = "output/eval",
    limit_days: int | None = None,
    runners: StageRunners | None = None,
    restart: bool = False,
    quota_limiter: EvaluationQuotaLimiter | None = None,
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
    models = tuple(dict.fromkeys((settings.llm.quick_llm, settings.llm.deep_llm)))
    if quota_limiter is None:
        quota_limiter = EvaluationQuotaLimiter(
            output_path / evaluation.quota_ledger_filename,
            models=models,
            max_rpm=evaluation.max_rpm,
            daily_budget=evaluation.daily_request_budget,
            quota_timezone=evaluation.quota_timezone,
        )

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
        expected_pairs = [
            (trade_date, ticker)
            for trade_date in trading_days
            for ticker in selected_tickers
        ]
        fingerprint = _evaluation_fingerprint(
            dataset_path=dataset_path,
            tickers=selected_tickers,
            trading_days=trading_days,
        )
        checkpoint_path = output_path / evaluation.checkpoint_filename
        checkpoint = _load_or_create_checkpoint(
            checkpoint_path,
            fingerprint=fingerprint,
            tickers=selected_tickers,
            trading_days=trading_days,
            models=models,
            limiter=quota_limiter,
            restart=restart,
        )
        decisions = [DecisionRecord(**record) for record in checkpoint["decisions"]]
        _validate_checkpoint_prefix(decisions, expected_pairs)

        if checkpoint["status"] != "complete":
            checkpoint["sessions"] = int(checkpoint["sessions"]) + 1
            _write_checkpoint(checkpoint_path, checkpoint)

        with TemporaryDirectory(prefix="lessons-", dir=output_path) as lessons_dir:
            lesson_store = LessonStore(lessons_dir)
            _restore_lessons(lesson_store, checkpoint["lessons"])
            with evaluation_quota_hook(quota_limiter):
                for trade_date, ticker in expected_pairs[len(decisions) :]:
                    remaining = min(quota_limiter.remaining(model) for model in models)
                    if remaining < evaluation.decision_request_reserve:
                        raise _paused(
                            quota_limiter,
                            model=models[0],
                            completed=len(decisions),
                            total=len(expected_pairs),
                            budget=evaluation.daily_request_budget,
                        )

                    print(f"Evaluating {ticker} on {trade_date}")
                    fetch_series = _point_in_time_fetcher(close_series, trade_date)
                    try:
                        rating = _run_decision_pipeline(
                            runners,
                            ticker=ticker,
                            trade_date=trade_date,
                            lesson_store=lesson_store,
                            fetch_series=fetch_series,
                        )
                    except Exception as exc:
                        if _contains_exception(exc, DailyQuotaReached):
                            raise _paused(
                                quota_limiter,
                                model=models[0],
                                completed=len(decisions),
                                total=len(expected_pairs),
                                budget=evaluation.daily_request_budget,
                            ) from exc
                        raise
                    close = dict(close_series[ticker])[trade_date]
                    decisions.append(
                        DecisionRecord(
                            date=trade_date,
                            ticker=ticker,
                            rating=rating,
                            close=close,
                        )
                    )
                    checkpoint["decisions"] = [
                        _decision_payload(record) for record in decisions
                    ]
                    checkpoint["lessons"] = _snapshot_lessons(
                        lesson_store, selected_tickers
                    )
                    checkpoint["llm_requests"] = _request_delta(
                        checkpoint, quota_limiter
                    )
                    _write_checkpoint(checkpoint_path, checkpoint)

    ticker_results = _score_tickers(
        selected_tickers,
        decisions,
        weight_over=evaluation.weight_over,
        weight_under=evaluation.weight_under,
    )
    markdown_path = output_path / "evaluation_report.md"
    csv_path = output_path / "evaluation_results.csv"
    llm_requests = _request_delta(checkpoint, quota_limiter)
    _write_markdown_report(
        markdown_path,
        trading_days=trading_days,
        decisions=decisions,
        ticker_results=ticker_results,
        start_date=evaluation.start_date,
        end_date=evaluation.end_date,
        quick_llm=settings.llm.quick_llm,
        deep_llm=settings.llm.deep_llm,
        max_rpm=evaluation.max_rpm,
        daily_request_budget=evaluation.daily_request_budget,
        llm_requests=llm_requests,
        sessions=int(checkpoint["sessions"]),
    )
    _write_csv_report(csv_path, decisions, ticker_results)
    checkpoint["status"] = "complete"
    checkpoint["llm_requests"] = llm_requests
    _write_checkpoint(checkpoint_path, checkpoint)

    return EvaluationResult(
        trading_days=tuple(trading_days),
        decisions=tuple(decisions),
        ticker_results=tuple(ticker_results),
        markdown_path=markdown_path,
        csv_path=csv_path,
        llm_requests=llm_requests,
        sessions=int(checkpoint["sessions"]),
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
    quick_llm: str,
    deep_llm: str,
    max_rpm: int,
    daily_request_budget: int,
    llm_requests: int,
    sessions: int,
) -> None:
    lines = [
        "# TradingAgents Evaluation",
        "",
        "> This evaluation invokes language models and can be expensive to run.",
        "",
        "Full evaluation command (rerun after midnight Pacific when paused):",
        "",
        "```bash",
        f"TRADING_AGENTS_LLM__QUICK_LLM={quick_llm} \\",
        f"TRADING_AGENTS_LLM__DEEP_LLM={deep_llm} \\",
        "uv run run-eval",
        "```",
        "",
        f"Period: {start_date}..{end_date} ({len(trading_days)} trading days)",
        "",
        "## Execution",
        "",
        f"- Quick LLM: `{quick_llm}`",
        f"- Deep LLM: `{deep_llm}`",
        f"- Rate limit: {max_rpm} requests/minute",
        f"- Evaluation daily budget: {daily_request_budget} requests",
        f"- Recorded LLM requests: {llm_requests}",
        f"- Sessions: {sessions}",
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
    _atomic_write_text(path, "\n".join(lines) + "\n")


def _write_csv_report(
    path: Path,
    decisions: Sequence[DecisionRecord],
    ticker_results: Sequence[TickerEvaluation],
) -> None:
    returns = {
        result.ticker: result.cumulative_return for result in ticker_results
    }
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
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
    os.replace(temporary, path)


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


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
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Discard compatible evaluation progress, but preserve quota usage.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.limit_days is not None and args.limit_days < 1:
        raise SystemExit("--limit-days must be at least 1")

    os.environ["TRADING_AGENTS_EVALUATION__ENABLED"] = "true"
    get_settings.cache_clear()
    evaluation = get_settings().evaluation
    try:
        result = run_evaluation(
            dataset_path=evaluation.dataset_path,
            tickers=args.tickers or evaluation.tickers,
            limit_days=args.limit_days,
            restart=args.restart,
        )
    except EvaluationPaused as paused:
        print(str(paused))
        print(
            "Run the same command again after the Gemini quota resets at "
            f"{paused.next_reset.isoformat()}."
        )
        return 0

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
