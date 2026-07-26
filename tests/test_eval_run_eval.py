from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import json

import pytest
from crewai.events.listeners.tracing.utils import (
    set_suppress_tracing_messages,
    should_suppress_tracing_messages,
)

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation.quota import EvaluationQuotaLimiter, ModelQuota
from trading_agents.evaluation.run_eval import (
    EvaluationPaused,
    StageRunners,
    run_evaluation,
)
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
        expected = {
            "2024-01-02": (("2024-01-02", 100.0), ("2024-01-02", 100.0)),
            "2024-01-03": (("2024-01-03", 110.0), ("2024-01-03", 101.0)),
        }
        assert fetch_series("AAPL", trade_date)[-1] == expected[trade_date][0]
        assert fetch_series("SPY", trade_date)[-1] == expected[trade_date][1]
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
    assert [scenario.scale for scenario in result.ticker_results[0].scenarios] == [
        0.5,
        1.0,
        1.5,
    ]
    assert [
        scenario.cumulative_return
        for scenario in result.ticker_results[0].scenarios
    ] == pytest.approx([10.0, 10.0, 10.0])
    assert observed_lesson_counts == [0, 1]
    assert observed_pipeline == [
        (stage, date)
        for date in ("2024-01-02", "2024-01-03")
        for stage in ("analyst", "research", "trader", "risk", "portfolio")
    ]

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "language models and can be expensive" in markdown
    assert "uv run run-eval" in markdown
    assert "| AAPL | 0.5x | 0.2500 | 0.2500 | 100.0000 | +10.00% | +10.0000 |" in markdown
    assert "| AAPL | 1.0x | 0.5000 | 0.5000 | 100.0000 | +10.00% | +10.0000 |" in markdown
    assert "| AAPL | 1.5x | 0.7500 | 0.7500 | 100.0000 | +10.00% | +10.0000 |" in markdown
    assert (
        "| Ticker | Scale | weight_over | weight_under | V_start | CR | "
        "Final capital |" in markdown
    )
    assert "| 2024-01-02 | AAPL | Buy | 100.0000 |" in markdown

    with result.csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["rating"] for row in rows] == ["Buy", "Hold"]
    assert list(rows[0]) == [
        "date",
        "ticker",
        "rating",
        "close",
        "capital_0_5x",
        "capital_1_0x",
        "capital_1_5x",
    ]
    for capital_column in ("capital_0_5x", "capital_1_0x", "capital_1_5x"):
        assert [row[capital_column] for row in rows] == ["-100", "10"]
    assert not list((tmp_path / "output").glob("lessons-*"))


def test_run_evaluation_scopes_tracing_message_suppression(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [("2024-01-02", 100)])
        dataset.put_prices("AAPL", [("2024-01-02", 100)])

    observed_suppression: list[bool] = []

    def analyst(_inputs):
        observed_suppression.append(should_suppress_tracing_messages())
        return {}

    def failing_analyst(_inputs):
        observed_suppression.append(should_suppress_tracing_messages())
        raise RuntimeError("injected tracing-scope failure")

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    previous = should_suppress_tracing_messages()
    try:
        set_suppress_tracing_messages(False)
        run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            output_dir=tmp_path / "success",
            runners=_simple_runners(analyst),
        )
        assert observed_suppression == [True]
        assert not should_suppress_tracing_messages()

        with pytest.raises(RuntimeError, match="injected tracing-scope failure"):
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                output_dir=tmp_path / "failure",
                runners=_simple_runners(failing_analyst),
            )
        assert observed_suppression == [True, True]
        assert not should_suppress_tracing_messages()

        set_suppress_tracing_messages(True)
        run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            output_dir=tmp_path / "already-suppressed",
            runners=_simple_runners(analyst),
        )
        assert observed_suppression == [True, True, True]
        assert should_suppress_tracing_messages()
    finally:
        set_suppress_tracing_messages(previous)
        get_settings.cache_clear()


def test_run_evaluation_rejects_scaled_weights_before_agent_execution(
    monkeypatch, tmp_path
):
    called = False

    def analyst(_inputs):
        nonlocal called
        called = True
        return {}

    output_dir = tmp_path / "output"
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__WEIGHT_OVER", "0.7")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match=r"1\.5x evaluation weight pair"):
            run_evaluation(
                dataset_path=tmp_path / "not-opened.duckdb",
                tickers=["AAPL"],
                output_dir=output_dir,
                runners=_simple_runners(analyst),
            )
    finally:
        get_settings.cache_clear()

    assert called is False
    assert not output_dir.exists()


def test_run_evaluation_pauses_then_resumes_without_overwriting_final_reports(
    monkeypatch, tmp_path
):
    dataset_path = tmp_path / "eval.duckdb"
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [(date, 100 + index) for index, date in enumerate(dates)])
        dataset.put_prices("AAPL", [(date, 100 + index) for index, date in enumerate(dates)])

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    report = output_dir / "evaluation_report.md"
    csv_path = output_dir / "evaluation_results.csv"
    report.write_text("old report\n", encoding="utf-8")
    csv_path.write_text("old csv\n", encoding="utf-8")

    current = [datetime(2026, 7, 19, 8, tzinfo=UTC)]
    sleeps: list[float] = []

    def now():
        return current[0]

    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__DAILY_REQUEST_BUDGET", "2")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__DECISION_REQUEST_RESERVE", "1")
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gemini/test")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "gemini/test")
    get_settings.cache_clear()

    seen: list[str] = []
    limiter = EvaluationQuotaLimiter(
        output_dir / "evaluation_quota.json",
        policies={"gemini/test": ModelQuota(15, 2, 1)},
        quota_timezone="America/Los_Angeles",
        now=now,
        sleep=sleep,
    )

    def analyst(inputs):
        limiter.acquire("gemini/test")
        seen.append(inputs["trade_date"])
        return {
            "market_report": "market",
            "sentiment_report": "sentiment",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
        }

    try:
        with pytest.raises(EvaluationPaused) as raised:
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                output_dir=output_dir,
                runners=_simple_runners(analyst),
                quota_limiter=limiter,
            )
        assert raised.value.completed == 2
        assert raised.value.model == "gemini/test"
        assert raised.value.roles == ("quick", "deep")
        assert raised.value.used == 2
        assert raised.value.budget == 2
        assert seen == dates[:2]
        assert report.read_text(encoding="utf-8") == "old report\n"
        assert csv_path.read_text(encoding="utf-8") == "old csv\n"
        checkpoint = json.loads(
            (output_dir / "evaluation_checkpoint.json").read_text(encoding="utf-8")
        )
        assert len(checkpoint["decisions"]) == 2

        current[0] += timedelta(days=1)
        resumed_limiter = EvaluationQuotaLimiter(
            output_dir / "evaluation_quota.json",
            policies={"gemini/test": ModelQuota(15, 2, 1)},
            quota_timezone="America/Los_Angeles",
            now=now,
            sleep=sleep,
        )
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            output_dir=output_dir,
            runners=_simple_runners(analyst),
            quota_limiter=resumed_limiter,
        )
    finally:
        get_settings.cache_clear()

    assert seen == dates
    assert len(result.decisions) == 3
    assert result.sessions == 2
    assert "old report" not in report.read_text(encoding="utf-8")
    assert len(list(csv.DictReader(csv_path.open(encoding="utf-8")))) == 3


def test_run_evaluation_reports_independent_quick_and_deep_quotas(
    monkeypatch, tmp_path
):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [("2024-01-02", 100)])
        dataset.put_prices("AAPL", [("2024-01-02", 100)])

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gemini/quick")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "openai/deep")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__QUICK_MAX_RPM", "15")
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__QUICK_DAILY_REQUEST_BUDGET", "500"
    )
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__QUICK_DECISION_REQUEST_RESERVE", "20"
    )
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__DEEP_MAX_RPM", "300")
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__DEEP_DAILY_REQUEST_BUDGET", "10000"
    )
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__DEEP_DECISION_REQUEST_RESERVE", "5"
    )
    get_settings.cache_clear()
    try:
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            output_dir=tmp_path / "output",
            runners=_simple_runners(lambda _inputs: {}),
        )
    finally:
        get_settings.cache_clear()

    report = result.markdown_path.read_text(encoding="utf-8")
    assert "| Quick | `gemini/quick` | 15 | 500 | 20 | 0 |" in report
    assert "| Deep | `openai/deep` | 300 | 10000 | 5 | 0 |" in report
    assert "TRADING_AGENTS_EVALUATION__QUICK_MAX_RPM=15" in report
    assert "TRADING_AGENTS_EVALUATION__DEEP_MAX_RPM=300" in report


def test_run_evaluation_pauses_on_constrained_deep_model(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [(date, 100) for date in dates])
        dataset.put_prices("AAPL", [(date, 100) for date in dates])

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gemini/quick")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "openai/deep")
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__QUICK_DAILY_REQUEST_BUDGET", "5"
    )
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__QUICK_DECISION_REQUEST_RESERVE", "1"
    )
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__DEEP_DAILY_REQUEST_BUDGET", "2"
    )
    monkeypatch.setenv(
        "TRADING_AGENTS_EVALUATION__DEEP_DECISION_REQUEST_RESERVE", "1"
    )
    get_settings.cache_clear()

    current = [datetime(2026, 7, 19, 8, tzinfo=UTC)]

    def now():
        return current[0]

    def sleep(seconds):
        current[0] += timedelta(seconds=seconds)

    policies = {
        "gemini/quick": ModelQuota(15, 5, 1),
        "openai/deep": ModelQuota(15, 2, 1),
    }
    limiter = EvaluationQuotaLimiter(
        tmp_path / "output" / "evaluation_quota.json",
        policies=policies,
        quota_timezone="America/Los_Angeles",
        now=now,
        sleep=sleep,
    )

    def analyst(_inputs):
        limiter.acquire("gemini/quick")
        return {}

    def research(_inputs):
        limiter.acquire("openai/deep")
        return {"investment_plan": {"plan": "hold"}}

    base = _simple_runners(analyst)
    runners = StageRunners(
        analyst, research, base.trader, base.risk, base.portfolio
    )
    try:
        with pytest.raises(EvaluationPaused) as raised:
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                output_dir=tmp_path / "output",
                runners=runners,
                quota_limiter=limiter,
            )
    finally:
        get_settings.cache_clear()

    assert raised.value.completed == 2
    assert raised.value.model == "openai/deep"
    assert raised.value.roles == ("deep",)
    assert raised.value.used == 2
    assert raised.value.budget == 2
    checkpoint = json.loads(
        (tmp_path / "output" / "evaluation_checkpoint.json").read_text()
    )
    assert checkpoint["llm_requests"] == 4
    assert checkpoint["llm_requests_by_model"] == {
        "gemini/quick": 2,
        "openai/deep": 2,
    }


def test_run_evaluation_rejects_different_limits_for_one_model(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gemini/shared")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "shared")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__QUICK_MAX_RPM", "15")
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__DEEP_MAX_RPM", "60")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="same model quota bucket"):
            run_evaluation(
                dataset_path=tmp_path / "missing.duckdb",
                tickers=["AAPL"],
                output_dir=tmp_path / "output",
                runners=_simple_runners(lambda _inputs: {}),
            )
    finally:
        get_settings.cache_clear()


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


def test_checkpoint_mismatch_requires_explicit_restart(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    prices = [("2024-01-02", 100), ("2024-01-03", 101)]
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", prices)
        dataset.put_prices("AAPL", prices)

    output_dir = tmp_path / "output"
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            limit_days=1,
            output_dir=output_dir,
            runners=_simple_runners(lambda _inputs: {}),
        )
        with pytest.raises(ValueError, match="use --restart"):
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                limit_days=2,
                output_dir=output_dir,
                runners=_simple_runners(lambda _inputs: {}),
            )
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL"],
            limit_days=2,
            output_dir=output_dir,
            runners=_simple_runners(lambda _inputs: {}),
            restart=True,
        )
    finally:
        get_settings.cache_clear()

    assert len(result.decisions) == 2
    assert (output_dir / "evaluation_quota.json").exists()


def test_failed_decision_does_not_commit_its_lesson(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    prices = [("2024-01-02", 100), ("2024-01-03", 101)]
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", prices)
        dataset.put_prices("AAPL", prices)

    def portfolio(inputs, *, store, **_kwargs):
        trade_date = inputs["trade_date"]
        store.append(
            "AAPL",
            LessonRecord(
                ticker="AAPL", trade_date=trade_date, final_decision="Hold"
            ),
        )
        if trade_date == "2024-01-03":
            raise RuntimeError("injected failure")
        return {"final_trade_decision": {"rating": "Hold"}, "lessons": []}

    base = _simple_runners(lambda _inputs: {})
    runners = StageRunners(
        base.analyst, base.research, base.trader, base.risk, portfolio
    )
    output_dir = tmp_path / "output"
    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            run_evaluation(
                dataset_path=dataset_path,
                tickers=["AAPL"],
                output_dir=output_dir,
                runners=runners,
            )
    finally:
        get_settings.cache_clear()

    checkpoint = json.loads(
        (output_dir / "evaluation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert [row["date"] for row in checkpoint["decisions"]] == ["2024-01-02"]
    assert [row["trade_date"] for row in checkpoint["lessons"]["AAPL"]] == [
        "2024-01-02"
    ]


def test_mocked_full_evaluation_writes_all_183_decisions(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    start = datetime(2024, 1, 2, tzinfo=UTC)
    dates = [(start + timedelta(days=index)).date().isoformat() for index in range(61)]
    with EvalDataset(dataset_path) as dataset:
        dataset.put_prices("SPY", [(date, 100 + index) for index, date in enumerate(dates)])
        for ticker in ("AAPL", "GOOGL", "AMZN"):
            dataset.put_prices(
                ticker, [(date, 100 + index) for index, date in enumerate(dates)]
            )

    monkeypatch.setenv("TRADING_AGENTS_EVALUATION__ENABLED", "true")
    get_settings.cache_clear()
    try:
        result = run_evaluation(
            dataset_path=dataset_path,
            tickers=["AAPL", "GOOGL", "AMZN"],
            output_dir=tmp_path / "output",
            runners=_simple_runners(lambda _inputs: {}),
        )
    finally:
        get_settings.cache_clear()

    assert len(result.decisions) == 183
    assert result.decisions[0].ticker == "AAPL"
    assert result.decisions[-1].ticker == "AMZN"


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
