from __future__ import annotations

import csv

import pytest

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation.run_eval import StageRunners, run_evaluation
from trading_agents.schemas import LessonRecord


def test_run_evaluation_processes_days_chronologically_and_writes_reports(
    monkeypatch, tmp_path
):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [("2024-01-02", 100), ("2024-01-03", 101)])
        dataset.put_prices("AAPL", [("2024-01-02", 100), ("2024-01-03", 110)])

    observed_pipeline: list[tuple[str, str]] = []
    observed_lesson_counts: list[int] = []

    def analyst(inputs):
        observed_pipeline.append(("analyst", inputs["trade_date"]))
        return {
            "market_report": "market",
            "sentiment_report": "sentiment",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
        }

    def research(inputs):
        observed_pipeline.append(("research", inputs["trade_date"]))
        return {"debate_history": "debate", "investment_plan": {"plan": "buy"}}

    def trader(inputs):
        observed_pipeline.append(("trader", inputs["trade_date"]))
        return {"trader_plan": {"action": "buy"}}

    def risk(inputs):
        observed_pipeline.append(("risk", inputs["trade_date"]))
        return {"risk_debate_history": "risk"}

    def portfolio(inputs, *, store, fetch_series):
        trade_date = inputs["trade_date"]
        observed_pipeline.append(("portfolio", trade_date))
        observed_lesson_counts.append(len(store.load("AAPL").lessons))
        assert fetch_series("AAPL", trade_date)[-1] == ("2024-01-03", 110.0)
        assert fetch_series("SPY", trade_date)[-1] == ("2024-01-03", 101.0)
        rating = "Buy" if trade_date == "2024-01-02" else "Hold"
        store.append(
            "AAPL",
            LessonRecord(
                ticker="AAPL", trade_date=trade_date, final_decision=rating
            ),
        )
        return {"final_trade_decision": {"rating": rating}, "lessons": []}

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["aapl"],
            output_dir=tmp_path / "output",
            runners=StageRunners(analyst, research, trader, risk, portfolio),
        )
    finally:
        get_settings.cache_clear()

    assert result.trading_days == ("2024-01-02", "2024-01-03")
    assert [record.rating for record in result.decisions] == ["Buy", "Hold"]
    assert result.ticker_results[0].cumulative_return == pytest.approx(10.0)
    assert observed_lesson_counts == [0, 1]
    assert observed_pipeline == [
        (stage, date)
        for date in ("2024-01-02", "2024-01-03")
        for stage in ("analyst", "research", "trader", "risk", "portfolio")
    ]

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "language models and can be expensive" in markdown
    assert "| AAPL | +10.00% |" in markdown
    assert "| 2024-01-02 | AAPL | Buy | 100.0000 |" in markdown

    with result.csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["rating"] for row in rows] == ["Buy", "Hold"]
    assert {row["cumulative_return_pct"] for row in rows} == {"10"}
    assert not list((tmp_path / "output").glob("lessons-*"))


def test_run_evaluation_applies_ticker_and_day_limits(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        prices = [("2024-01-02", 100), ("2024-01-03", 101)]
        dataset.put_prices("SPY", prices)
        dataset.put_prices("AAPL", prices)
        dataset.put_prices("GOOGL", prices)

    seen: list[tuple[str, str]] = []

    def analyst(inputs):
        seen.append((inputs["ticker"], inputs["trade_date"]))
        return {
            "market_report": "market",
            "sentiment_report": "sentiment",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
        }

    runners = _simple_runners(analyst)
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["googl"],
            limit_days=1,
            output_dir=tmp_path / "output",
            runners=runners,
        )
    finally:
        get_settings.cache_clear()

    assert seen == [("GOOGL", "2024-01-02")]
    assert result.trading_days == ("2024-01-02",)
    assert result.ticker_results[0].ticker == "GOOGL"


def test_run_evaluation_fails_on_missing_ticker_close(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [("2024-01-02", 100), ("2024-01-03", 101)])
        dataset.put_prices("AAPL", [("2024-01-02", 100)])

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="missing AAPL closes for: 2024-01-03"):
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                output_dir=tmp_path / "output",
                runners=_simple_runners(lambda _inputs: {}),
            )
    finally:
        get_settings.cache_clear()


def test_run_evaluation_rejects_empty_tickers(tmp_path):
    with pytest.raises(ValueError, match="At least one non-empty ticker"):
        run_evaluation(
            dataset_path=tmp_path / "missing.duckdb",
            tickers=[],
            runners=_simple_runners(lambda _inputs: {}),
        )


def _simple_runners(analyst):
    def research(_inputs):
        return {"investment_plan": {"plan": "hold"}}

    def trader(_inputs):
        return {"trader_plan": {"action": "hold"}}

    def risk(_inputs):
        return {"risk_debate_history": "risk"}

    def portfolio(_inputs, **_kwargs):
        return {"final_trade_decision": {"rating": "Hold"}, "lessons": []}

    return StageRunners(analyst, research, trader, risk, portfolio)
