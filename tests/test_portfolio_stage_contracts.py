from types import SimpleNamespace

import pytest

from trading_agents.crews.portfolio_crew import portfolio_crew as portfolio_module
from trading_agents.crews.portfolio_crew.lesson_store import (
    NO_LESSONS_LINE,
    LessonStore,
    compute_holding_days,
    compute_realized_metrics,
    render_lessons_line,
    resolve_benchmark,
)
from trading_agents.crews.portfolio_crew.portfolio_crew import (
    normalize_rating,
    run_portfolio_stage,
)
from trading_agents.schemas import LessonRecord, PortfolioDecision, PortfolioRating


VALID_RATINGS = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}

PORTFOLIO_INPUTS = {
    "ticker": "NVDA",
    "trade_date": "2026-06-04",
    "investment_plan": {"recommendation": "Buy", "rationale": "strong"},
    "trader_plan": {"action": "Buy", "reasoning": "add exposure"},
    "risk_debate_history": "Aggressive Analyst: upside\n\nConservative Analyst: downside",
}


def _decision_result(rating: str = "Buy") -> SimpleNamespace:
    decision = PortfolioDecision(
        rating=PortfolioRating(rating),
        executive_summary="Enter on a pullback, size at 5%.",
        investment_thesis="The bull case outweighs the bear case.",
    )
    return SimpleNamespace(raw=decision.model_dump_json(), pydantic=decision)


# --- Input validation -------------------------------------------------------


def test_run_portfolio_stage_requires_upstream_artifacts(monkeypatch):
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("portfolio task kickoff should not run for invalid inputs")

    monkeypatch.setattr(portfolio_module, "_kickoff_portfolio_task", should_not_run)

    with pytest.raises(ValueError, match="trader_plan"):
        run_portfolio_stage(
            {
                "ticker": "NVDA",
                "investment_plan": {"recommendation": "Buy"},
                "risk_debate_history": "history",
            }
        )

    with pytest.raises(ValueError, match="risk_debate_history"):
        run_portfolio_stage(
            {
                "ticker": "NVDA",
                "investment_plan": {"recommendation": "Buy"},
                "trader_plan": {"action": "Buy"},
            }
        )

    assert calls == []


# --- Decision contract ------------------------------------------------------


def test_run_portfolio_stage_returns_valid_rating_with_no_prior_lessons(
    monkeypatch, tmp_path
):
    captured = []

    def fake_kickoff(task_name, inputs):
        captured.append((task_name, dict(inputs)))
        assert task_name == "final_decision"  # no prior lessons -> no self-reflection
        return _decision_result("Overweight")

    monkeypatch.setattr(portfolio_module, "_kickoff_portfolio_task", fake_kickoff)

    store = LessonStore(base_dir=tmp_path)
    result = run_portfolio_stage(PORTFOLIO_INPUTS, store=store)

    assert result["final_trade_decision"]["rating"] in VALID_RATINGS
    assert result["final_trade_decision"]["rating"] == "Overweight"
    assert result["lessons"] == []

    # No prior lessons -> {lessons_line} is the canonical fallback string.
    final_call = next(inputs for name, inputs in captured if name == "final_decision")
    assert final_call["lessons_line"] == NO_LESSONS_LINE

    # A fresh lesson record is persisted for this decision.
    book = store.load("NVDA")
    assert len(book.lessons) == 1
    assert book.lessons[0].trade_date == "2026-06-04"
    assert book.lessons[0].final_decision == "Overweight"


def test_run_portfolio_stage_updates_reflects_and_retrieves_prior_lessons(
    monkeypatch, tmp_path
):
    store = LessonStore(base_dir=tmp_path)
    store.append(
        "NVDA",
        LessonRecord(ticker="NVDA", trade_date="2026-05-01", final_decision="Buy"),
    )

    def fake_fetch(symbol, trade_date):
        # Instrument gains 2%, benchmark gains 1% over a one-day window.
        if symbol == "NVDA":
            return [("2026-05-01", 100.0), ("2026-05-02", 102.0)]
        return [("2026-05-01", 50.0), ("2026-05-02", 50.5), ("2026-05-05", 51.0)]

    calls = []

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        if task_name == "self_reflection":
            return SimpleNamespace(raw="The directional call was correct.", pydantic=None)
        return _decision_result("Hold")

    monkeypatch.setattr(portfolio_module, "_kickoff_portfolio_task", fake_kickoff)

    result = run_portfolio_stage(
        PORTFOLIO_INPUTS, store=store, fetch_series=fake_fetch
    )

    # Self-reflection ran before the final decision, with the realized figures.
    task_order = [name for name, _ in calls]
    assert task_order == ["self_reflection", "final_decision"]
    reflection_inputs = calls[0][1]
    assert reflection_inputs["benchmark_name"] == "SPY"
    assert reflection_inputs["raw_return"] == "+2.0%"
    assert reflection_inputs["alpha_return"] == "+1.0%"

    # The retrieved lessons carry the updated returns and the written reflection.
    assert len(result["lessons"]) == 1
    retrieved = result["lessons"][0]
    assert retrieved["raw_return"] == pytest.approx(0.02)
    assert retrieved["alpha_return"] == pytest.approx(0.01)
    assert retrieved["holding_days"] == 1
    assert retrieved["reflection"] == "The directional call was correct."

    # {lessons_line} fed to the final decision is non-empty rendered text.
    final_inputs = calls[1][1]
    assert final_inputs["lessons_line"] != NO_LESSONS_LINE
    assert "2026-05-01" in final_inputs["lessons_line"]

    # The store now holds the updated prior record plus the new decision record.
    book = store.load("NVDA")
    trade_dates = sorted(record.trade_date for record in book.lessons)
    assert trade_dates == ["2026-05-01", "2026-06-04"]


def test_run_portfolio_stage_reflects_each_prior_decision_only_once(
    monkeypatch, tmp_path
):
    store = LessonStore(base_dir=tmp_path)
    store.append(
        "NVDA",
        LessonRecord(
            ticker="NVDA",
            trade_date="2026-05-01",
            final_decision="Buy",
            reflection="Already reviewed.",
        ),
    )
    store.append(
        "NVDA",
        LessonRecord(ticker="NVDA", trade_date="2026-06-04", final_decision="Hold"),
    )
    calls = []

    def fake_kickoff(task_name, inputs):
        calls.append(task_name)
        assert task_name == "final_decision"
        return _decision_result("Hold")

    def should_not_fetch(*_args):
        raise AssertionError("No completed lesson needs another reflection")

    monkeypatch.setattr(portfolio_module, "_kickoff_portfolio_task", fake_kickoff)

    run_portfolio_stage(
        PORTFOLIO_INPUTS,
        store=store,
        fetch_series=should_not_fetch,
    )

    assert calls == ["final_decision"]
    assert store.load("NVDA").lessons[0].reflection == "Already reviewed."


# --- Malformed-output normalizer behavior -----------------------------------


def test_normalize_rating_accepts_trivial_variants():
    assert normalize_rating("Buy.") is PortfolioRating.BUY
    assert normalize_rating("BUY") is PortfolioRating.BUY
    assert normalize_rating("  sell  ") is PortfolioRating.SELL
    assert normalize_rating("BUY because the thesis is strong") is PortfolioRating.BUY
    assert normalize_rating(PortfolioRating.HOLD) is PortfolioRating.HOLD


def test_normalize_rating_rejects_ambiguous_or_unknown():
    with pytest.raises(ValueError):
        normalize_rating("Buy or Sell")
    with pytest.raises(ValueError):
        normalize_rating("Maybe later")


def test_run_portfolio_stage_normalizes_malformed_rating(monkeypatch, tmp_path):
    def fake_kickoff(task_name, inputs):
        raw = (
            '{"rating": "Buy.", '
            '"executive_summary": "Enter on a pullback.", '
            '"investment_thesis": "Bull case wins."}'
        )
        return SimpleNamespace(raw=raw, pydantic=None)

    monkeypatch.setattr(portfolio_module, "_kickoff_portfolio_task", fake_kickoff)

    store = LessonStore(base_dir=tmp_path)
    result = run_portfolio_stage(PORTFOLIO_INPUTS, store=store)

    assert result["final_trade_decision"]["rating"] == "Buy"
    assert type(result["final_trade_decision"]["rating"]) is str


# --- Lesson math ------------------------------------------------------------


def test_resolve_benchmark_from_suffix():
    assert resolve_benchmark("NVDA") == "SPY"
    assert resolve_benchmark("RY.TO") == "^GSPTSE"
    assert resolve_benchmark("7203.T") == "^N225"
    assert resolve_benchmark("0700.HK") == "^HSI"
    assert resolve_benchmark("RELIANCE.NS") == "^NSEI"


def test_holding_days_cap_example_from_prompts():
    # PROMPTS.md example: trade date 2026/06/04, instrument latest close 06/05
    # (1 transaction day), benchmark latest close 06/08 (2 transaction days,
    # weekend in between) -> holding days is 1.
    instrument = [("2026-06-04", 100.0), ("2026-06-05", 102.0)]
    benchmark = [("2026-06-04", 50.0), ("2026-06-05", 50.5), ("2026-06-08", 51.0)]
    assert compute_holding_days(instrument, benchmark, "2026-06-04", 5) == 1


def test_holding_days_is_capped_at_max():
    instrument = [("2026-06-04", 100.0)] + [
        (f"2026-06-{day:02d}", 100.0) for day in range(5, 20)
    ]
    benchmark = [("2026-06-04", 50.0)] + [
        (f"2026-06-{day:02d}", 50.0) for day in range(5, 20)
    ]
    assert compute_holding_days(instrument, benchmark, "2026-06-04", 5) == 5


def test_alpha_return_is_raw_minus_benchmark():
    instrument = [("2026-06-04", 100.0), ("2026-06-05", 110.0)]
    benchmark = [("2026-06-04", 50.0), ("2026-06-05", 51.0)]
    raw_return, alpha_return, holding_days = compute_realized_metrics(
        instrument, benchmark, "2026-06-04", 5
    )
    assert holding_days == 1
    assert raw_return == pytest.approx(0.10)
    benchmark_return = (51.0 - 50.0) / 50.0
    assert alpha_return == pytest.approx(raw_return - benchmark_return)


def test_benchmark_uses_latest_previous_close_when_trade_date_missing():
    # Benchmark has no close on the trade date; the latest previous date is used.
    instrument = [("2026-06-04", 100.0), ("2026-06-05", 102.0)]
    benchmark = [("2026-06-03", 50.0), ("2026-06-05", 51.0)]
    raw_return, alpha_return, holding_days = compute_realized_metrics(
        instrument, benchmark, "2026-06-04", 5
    )
    assert holding_days == 1
    benchmark_return = (51.0 - 50.0) / 50.0
    assert alpha_return == pytest.approx(raw_return - benchmark_return)


def test_render_lessons_line_falls_back_when_empty():
    assert render_lessons_line([]) == NO_LESSONS_LINE
