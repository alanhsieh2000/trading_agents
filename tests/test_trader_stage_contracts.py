from types import SimpleNamespace

import pytest

from trading_agents.crews.trader_crew import trader_crew as trader_module
from trading_agents.crews.trader_crew.trader_crew import run_trader_stage
from trading_agents.schemas import TraderAction, TraderProposal


TRADER_INPUTS = {
    "ticker": "SHOP.TO",
    "trade_date": "2024-05-24",
    "investment_plan": {
        "recommendation": "Buy",
        "rationale": "Bull case is stronger.",
        "strategic_actions": "Start a modest position.",
    },
}


def test_run_trader_stage_requires_ticker_before_kickoff(monkeypatch):
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("trader kickoff should not run when inputs are invalid")

    monkeypatch.setattr(trader_module.TraderCrew, "crew", should_not_run)

    with pytest.raises(ValueError, match="ticker"):
        run_trader_stage({"investment_plan": "plan"})

    assert calls == []


def test_run_trader_stage_requires_investment_plan_before_kickoff(monkeypatch):
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("trader kickoff should not run when inputs are invalid")

    monkeypatch.setattr(trader_module.TraderCrew, "crew", should_not_run)

    with pytest.raises(ValueError, match="investment_plan"):
        run_trader_stage({"ticker": "NVDA"})

    assert calls == []


def test_run_trader_stage_returns_stable_trader_plan(monkeypatch):
    captured_inputs = {}

    class FakeCrew:
        def kickoff(self, inputs):
            captured_inputs.update(inputs)
            proposal = TraderProposal(
                action=TraderAction.BUY,
                reasoning="The research plan supports adding exposure.",
                entry_price=102.5,
                stop_loss=94.0,
                position_sizing="5% of portfolio",
            )
            task_output = SimpleNamespace(raw=proposal.model_dump_json(), pydantic=proposal)
            return SimpleNamespace(raw=proposal.model_dump_json(), tasks_output=[task_output])

    monkeypatch.setattr(trader_module.TraderCrew, "crew", lambda self: FakeCrew())

    result = run_trader_stage(TRADER_INPUTS)

    assert captured_inputs["ticker"] == "SHOP.TO"
    assert '"recommendation": "Buy"' in captured_inputs["investment_plan"]
    assert result["trader_plan"] == TraderProposal(
        action=TraderAction.BUY,
        reasoning="The research plan supports adding exposure.",
        entry_price=102.5,
        stop_loss=94.0,
        position_sizing="5% of portfolio",
    )


def test_run_trader_stage_parses_raw_json_fallback(monkeypatch):
    class FakeCrew:
        def kickoff(self, inputs):
            raw = TraderProposal(
                action=TraderAction.HOLD,
                reasoning="The setup is balanced.",
                entry_price=None,
                stop_loss=None,
                position_sizing="Maintain current exposure",
            ).model_dump_json()
            return SimpleNamespace(raw=raw, tasks_output=[])

    monkeypatch.setattr(trader_module.TraderCrew, "crew", lambda self: FakeCrew())

    result = run_trader_stage(TRADER_INPUTS)

    assert result["trader_plan"].action == "Hold"
    assert result["trader_plan"].reasoning == "The setup is balanced."
    assert result["trader_plan"].entry_price is None
    assert result["trader_plan"].stop_loss is None
    assert result["trader_plan"].position_sizing == "Maintain current exposure"
