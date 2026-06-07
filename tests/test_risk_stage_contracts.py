from types import SimpleNamespace

import pytest

from trading_agents.config import get_settings
from trading_agents.crews.risk_management_crew import risk_management_crew as risk_module
from trading_agents.crews.risk_management_crew.risk_management_crew import run_risk_stage


RISK_INPUTS = {
    "ticker": "NVDA",
    "trade_date": "2024-05-24",
    "market_report": "market report",
    "sentiment_report": "sentiment report",
    "news_report": "news report",
    "fundamentals_report": "fundamentals report",
    "trader_plan": {
        "action": "Buy",
        "reasoning": "The research plan supports adding exposure.",
        "entry_price": 102.5,
        "stop_loss": 94.0,
        "position_sizing": "5% of portfolio",
    },
}


def test_run_risk_stage_requires_reports_and_trader_plan_before_kickoff(monkeypatch):
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("risk task kickoff should not run when inputs are invalid")

    monkeypatch.setattr(risk_module, "_kickoff_risk_task", should_not_run)

    with pytest.raises(ValueError, match="fundamentals_report"):
        run_risk_stage(
            {
                "ticker": "NVDA",
                "market_report": "market report",
                "sentiment_report": "sentiment report",
                "news_report": "news report",
                "trader_plan": "plan",
            }
        )

    with pytest.raises(ValueError, match="trader_plan"):
        run_risk_stage(
            {
                "ticker": "NVDA",
                "market_report": "market report",
                "sentiment_report": "sentiment report",
                "news_report": "news report",
                "fundamentals_report": "fundamentals report",
            }
        )

    assert calls == []


def test_run_risk_stage_accumulates_history_in_order(monkeypatch):
    calls = []
    responses = {
        "aggressive_risk_analysis": [_task_result("Aggressive round 1")],
        "conservative_risk_analysis": [_task_result("Conservative round 1")],
        "neutral_risk_analysis": [_task_result("Neutral round 1")],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(risk_module, "_kickoff_risk_task", fake_kickoff)

    result = run_risk_stage(RISK_INPUTS, max_rounds=1)

    assert [task_name for task_name, _ in calls] == [
        "aggressive_risk_analysis",
        "conservative_risk_analysis",
        "neutral_risk_analysis",
    ]
    assert calls[0][1]["history"] == ""
    assert calls[0][1]["current_conservative_response"] == ""
    assert calls[0][1]["current_neutral_response"] == ""
    assert '"action": "Buy"' in calls[0][1]["trader_plan"]
    assert calls[0][1]["market_research_report"] == "market report"
    assert "Aggressive round 1" in calls[1][1]["history"]
    assert calls[1][1]["current_aggressive_response"].startswith("Aggressive Analyst: ")
    assert "Conservative round 1" in calls[2][1]["history"]
    assert calls[2][1]["current_conservative_response"].startswith(
        "Conservative Analyst: "
    )

    history = result["risk_debate_history"]
    assert history.index("Aggressive round 1") < history.index("Conservative round 1")
    assert history.index("Conservative round 1") < history.index("Neutral round 1")


def test_run_risk_stage_runs_exactly_max_rounds(monkeypatch):
    calls = []
    responses = {
        "aggressive_risk_analysis": [
            _task_result("Aggressive round 1"),
            _task_result("Aggressive round 2"),
            _task_result("Aggressive round 3"),
        ],
        "conservative_risk_analysis": [
            _task_result("Conservative round 1"),
            _task_result("Conservative round 2"),
            _task_result("Conservative round 3"),
        ],
        "neutral_risk_analysis": [
            _task_result("Neutral round 1"),
            _task_result("Neutral round 2"),
            _task_result("Neutral round 3"),
        ],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(risk_module, "_kickoff_risk_task", fake_kickoff)

    result = run_risk_stage(RISK_INPUTS, max_rounds=3)

    assert [task_name for task_name, _ in calls] == [
        "aggressive_risk_analysis",
        "conservative_risk_analysis",
        "neutral_risk_analysis",
        "aggressive_risk_analysis",
        "conservative_risk_analysis",
        "neutral_risk_analysis",
        "aggressive_risk_analysis",
        "conservative_risk_analysis",
        "neutral_risk_analysis",
    ]
    assert calls[3][1]["current_conservative_response"].startswith(
        "Conservative Analyst: "
    )
    assert calls[3][1]["current_neutral_response"].startswith("Neutral Analyst: ")
    assert "Aggressive round 1" in calls[3][1]["history"]
    assert "Neutral round 1" in calls[3][1]["history"]
    assert "Aggressive round 2" in result["risk_debate_history"]
    assert "Neutral round 3" in result["risk_debate_history"]


def test_run_risk_stage_uses_settings_max_rounds_default(monkeypatch):
    monkeypatch.delenv("TRADING_AGENTS_RISK_STAGE__MAX_ROUNDS", raising=False)
    get_settings.cache_clear()
    calls = []
    responses = {
        "aggressive_risk_analysis": [_task_result("Aggressive round 1")],
        "conservative_risk_analysis": [_task_result("Conservative round 1")],
        "neutral_risk_analysis": [_task_result("Neutral round 1")],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(risk_module, "_kickoff_risk_task", fake_kickoff)

    result = run_risk_stage(RISK_INPUTS)

    assert len(calls) == 3
    assert "Aggressive round 1" in result["risk_debate_history"]
    get_settings.cache_clear()


def test_run_risk_stage_honors_settings_max_rounds_override(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_RISK_STAGE__MAX_ROUNDS", "2")
    get_settings.cache_clear()
    calls = []
    responses = {
        "aggressive_risk_analysis": [
            _task_result("Aggressive round 1"),
            _task_result("Aggressive round 2"),
        ],
        "conservative_risk_analysis": [
            _task_result("Conservative round 1"),
            _task_result("Conservative round 2"),
        ],
        "neutral_risk_analysis": [
            _task_result("Neutral round 1"),
            _task_result("Neutral round 2"),
        ],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(risk_module, "_kickoff_risk_task", fake_kickoff)

    result = run_risk_stage(RISK_INPUTS)

    assert len(calls) == 6
    assert "Aggressive round 2" in result["risk_debate_history"]
    assert "Neutral round 2" in result["risk_debate_history"]
    get_settings.cache_clear()


def _task_result(raw: str) -> SimpleNamespace:
    return SimpleNamespace(raw=raw, pydantic=None)
