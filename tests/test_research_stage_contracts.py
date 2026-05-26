from types import SimpleNamespace

import pytest

from trading_agents.crews.research_crew import research_crew as research_module
from trading_agents.crews.research_crew.research_crew import run_research_stage
from trading_agents.schemas import InvestmentPlan


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


def test_run_research_stage_accumulates_history_in_order_and_stops_early(monkeypatch):
    calls = []
    responses = {
        "bull_research": [
            _task_result("Bull round 1\nHAS_MORE: no"),
        ],
        "bear_research": [
            _task_result("Bear round 1\nHAS_MORE: no"),
        ],
        "research_management": [
            _manager_result("Hold", "Balanced setup"),
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
    ]
    assert calls[0][1]["debate_history"] == ""
    assert "Bull round 1" in calls[1][1]["debate_history"]
    assert "Bull round 1" in calls[2][1]["debate_history"]
    assert "Bear round 1" in calls[2][1]["debate_history"]
    assert result["debate_history"].index("Bull round 1") < result["debate_history"].index(
        "Bear round 1"
    )
    assert result["investment_plan"] == {
        "rating": "Hold",
        "thesis": "Balanced setup",
        "supporting_evidence": ["supporting evidence"],
        "key_risks": ["key risk"],
        "recommended_action": "Monitor closely",
    }


def test_run_research_stage_runs_multiple_rounds_until_both_sides_stop(monkeypatch):
    calls = []
    responses = {
        "bull_research": [
            _task_result("Bull round 1\nHAS_MORE: yes"),
            _task_result("Bull round 2\nHAS_MORE: no"),
        ],
        "bear_research": [
            _task_result("Bear round 1\nHAS_MORE: yes"),
            _task_result("Bear round 2\nHAS_MORE: no"),
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

    result = run_research_stage(RESEARCH_INPUTS, max_rounds=3)

    assert [task_name for task_name, _ in calls] == [
        "bull_research",
        "bear_research",
        "research_management",
        "bull_research",
        "bear_research",
        "research_management",
    ]
    assert "Bear round 1" in calls[3][1]["debate_history"]
    assert result["debate_history"].index("Bull round 1") < result["debate_history"].index(
        "Bear round 1"
    )
    assert result["debate_history"].index("Bear round 1") < result["debate_history"].index(
        "Bull round 2"
    )
    assert result["debate_history"].index("Bull round 2") < result["debate_history"].index(
        "Bear round 2"
    )
    assert result["investment_plan"]["rating"] == "Buy"
    assert result["investment_plan"]["thesis"] == "Round two thesis"


def _task_result(raw: str) -> SimpleNamespace:
    return SimpleNamespace(raw=raw, pydantic=None)


def _manager_result(rating: str, thesis: str) -> SimpleNamespace:
    return SimpleNamespace(
        raw=f"{rating}: {thesis}",
        pydantic=InvestmentPlan(
            rating=rating,
            thesis=thesis,
            supporting_evidence=["supporting evidence"],
            key_risks=["key risk"],
            recommended_action="Monitor closely",
        ),
    )
