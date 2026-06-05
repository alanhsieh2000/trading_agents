from types import SimpleNamespace

import pytest

from trading_agents.crews.research_crew import research_crew as research_module
from trading_agents.crews.research_crew.research_crew import run_research_stage
from trading_agents.config import get_settings
from trading_agents.schemas import InvestmentPlan, PortfolioRating


RESEARCH_INPUTS = {
    "ticker": "NVDA",
    "trade_date": "2024-05-24",
    "market_report": "market report",
    "sentiment_report": "sentiment report",
    "news_report": "news report",
    "fundamentals_report": "fundamentals report",
}


def test_run_research_stage_requires_all_analyst_reports(monkeypatch):
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("research task kickoff should not run when inputs are invalid")

    monkeypatch.setattr(research_module, "_kickoff_research_task", should_not_run)

    with pytest.raises(ValueError, match="fundamentals_report"):
        run_research_stage(
            {
                "market_report": "market report",
                "sentiment_report": "sentiment report",
                "news_report": "news report",
            }
        )

    assert calls == []


def test_run_research_stage_accumulates_history_in_order(monkeypatch):
    calls = []
    responses = {
        "bull_research": [
            _task_result("Bull round 1"),
        ],
        "bear_research": [
            _task_result("Bear round 1"),
        ],
        "research_management": [
            _manager_result("Hold", "Balanced setup"),
        ],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(research_module, "_kickoff_research_task", fake_kickoff)

    result = run_research_stage(RESEARCH_INPUTS, max_rounds=1)

    assert [task_name for task_name, _ in calls] == [
        "bull_research",
        "bear_research",
        "research_management",
    ]
    assert calls[0][1]["history"] == ""
    assert calls[0][1]["current_response"] == ""
    assert calls[0][1]["fundamentals_label"] == "Company fundamentals report"
    assert calls[1][1]["current_response"].startswith("Bull Analyst: ")
    assert "Bull round 1" in calls[1][1]["history"]
    assert calls[2][1]["current_response"].startswith("Bear Analyst: ")
    assert "Bull round 1" in calls[2][1]["history"]
    assert "Bear round 1" in calls[2][1]["history"]
    assert result["debate_history"].index("Bull round 1") < result["debate_history"].index(
        "Bear round 1"
    )
    assert result["investment_plan"] == {
        "recommendation": "Hold",
        "rationale": "Balanced setup",
        "strategic_actions": "Monitor closely",
    }


def test_run_research_stage_runs_exactly_max_rounds(monkeypatch):
    calls = []
    responses = {
        "bull_research": [
            _task_result("Bull round 1"),
            _task_result("Bull round 2"),
            _task_result("Bull round 3"),
        ],
        "bear_research": [
            _task_result("Bear round 1"),
            _task_result("Bear round 2"),
            _task_result("Bear round 3"),
        ],
        "research_management": [
            _manager_result("Hold", "Round one thesis"),
            _manager_result("Overweight", "Round two thesis"),
            _manager_result("Buy", "Round three thesis"),
        ],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(research_module, "_kickoff_research_task", fake_kickoff)

    result = run_research_stage(RESEARCH_INPUTS, max_rounds=3)

    assert [task_name for task_name, _ in calls] == [
        "bull_research",
        "bear_research",
        "research_management",
        "bull_research",
        "bear_research",
        "research_management",
        "bull_research",
        "bear_research",
        "research_management",
    ]
    assert calls[3][1]["current_response"].startswith("Bear Analyst: ")
    assert "Bear round 1" in calls[3][1]["history"]
    assert result["debate_history"].index("Bull round 1") < result["debate_history"].index(
        "Bear round 1"
    )
    assert result["debate_history"].index("Bear round 1") < result["debate_history"].index(
        "Bull round 2"
    )
    assert result["debate_history"].index("Bull round 2") < result["debate_history"].index(
        "Bear round 2"
    )
    assert result["debate_history"].index("Bear round 2") < result["debate_history"].index(
        "Bull round 3"
    )
    assert result["debate_history"].index("Bull round 3") < result["debate_history"].index(
        "Bear round 3"
    )
    assert result["investment_plan"]["recommendation"] == "Buy"
    assert result["investment_plan"]["rationale"] == "Round three thesis"


def test_run_research_stage_uses_settings_max_rounds_by_default(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_RESEARCH_STAGE__MAX_ROUNDS", "2")
    get_settings.cache_clear()
    calls = []
    responses = {
        "bull_research": [
            _task_result("Bull round 1"),
            _task_result("Bull round 2"),
        ],
        "bear_research": [
            _task_result("Bear round 1"),
            _task_result("Bear round 2"),
        ],
        "research_management": [
            _manager_result("Hold", "Round one thesis"),
            _manager_result("Buy", "Round two thesis"),
        ],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(research_module, "_kickoff_research_task", fake_kickoff)

    result = run_research_stage(RESEARCH_INPUTS)

    assert [task_name for task_name, _ in calls] == [
        "bull_research",
        "bear_research",
        "research_management",
        "bull_research",
        "bear_research",
        "research_management",
    ]
    assert result["investment_plan"]["rationale"] == "Round two thesis"
    get_settings.cache_clear()


def test_run_research_stage_sets_crypto_fundamentals_label(monkeypatch):
    calls = []
    responses = {
        "bull_research": [_task_result("Bull crypto")],
        "bear_research": [_task_result("Bear crypto")],
        "research_management": [_manager_result("Hold", "Crypto setup")],
    }

    def fake_kickoff(task_name, inputs):
        calls.append((task_name, dict(inputs)))
        return responses[task_name].pop(0)

    monkeypatch.setattr(research_module, "_kickoff_research_task", fake_kickoff)

    run_research_stage({**RESEARCH_INPUTS, "ticker": "btc-usd"}, max_rounds=1)

    assert calls[0][1]["ticker"] == "btc-usd"
    assert (
        calls[0][1]["fundamentals_label"]
        == "Asset fundamentals report (may be unavailable for crypto)"
    )


def _task_result(raw: str) -> SimpleNamespace:
    return SimpleNamespace(raw=raw, pydantic=None)


def _manager_result(rating: str, thesis: str) -> SimpleNamespace:
    return SimpleNamespace(
        raw=f"{rating}: {thesis}",
        pydantic=InvestmentPlan(
            recommendation=PortfolioRating(rating),
            rationale=thesis,
            strategic_actions="Monitor closely",
        ),
    )
