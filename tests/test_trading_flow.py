from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_agents import main as main_module


REPORTS = {
    "fundamentals_report": "fundamentals text",
    "sentiment_report": "sentiment text",
    "news_report": "news text",
    "market_report": "market text",
}
RESEARCH_OUTPUTS = {
    "debate_history": "Bull Analyst: bull text\n\nBear Analyst: bear text",
    "investment_plan": {
        "recommendation": "Buy",
        "rationale": "research rationale",
        "strategic_actions": "increase exposure",
    },
}
TRADER_OUTPUTS = {
    "trader_plan": {
        "action": "Buy",
        "reasoning": "The research plan supports adding exposure.",
        "entry_price": 102.5,
        "stop_loss": 94.0,
        "position_sizing": "5% of portfolio",
    },
}
RISK_OUTPUTS = {
    "risk_debate_history": (
        "Aggressive Analyst: upside case\n\n"
        "Conservative Analyst: downside case\n\n"
        "Neutral Analyst: balanced case"
    ),
}
PORTFOLIO_OUTPUTS = {
    "final_trade_decision": {
        "rating": "Buy",
        "executive_summary": "Enter on a pullback, size at 5%.",
        "investment_thesis": "The bull case outweighs the bear case.",
        "price_target": 150.0,
        "time_horizon": "3-6 months",
    },
    "lessons": [],
}


def test_trading_agents_flow_runs_analyst_stage_with_trigger(monkeypatch, tmp_path):
    captured_inputs = {}
    captured_research_inputs = {}
    captured_trader_inputs = {}
    captured_risk_inputs = {}
    captured_portfolio_inputs = {}

    def fake_run_analyst_stage(inputs):
        captured_inputs.update(inputs)
        return dict(REPORTS)

    def fake_run_research_stage(inputs):
        captured_research_inputs.update(inputs)
        return dict(RESEARCH_OUTPUTS)

    def fake_run_trader_stage(inputs):
        captured_trader_inputs.update(inputs)
        return dict(TRADER_OUTPUTS)

    def fake_run_risk_stage(inputs):
        captured_risk_inputs.update(inputs)
        return dict(RISK_OUTPUTS)

    def fake_run_portfolio_stage(inputs):
        captured_portfolio_inputs.update(inputs)
        return dict(PORTFOLIO_OUTPUTS)

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)
    monkeypatch.setattr(main_module, "run_research_stage", fake_run_research_stage)
    monkeypatch.setattr(main_module, "run_trader_stage", fake_run_trader_stage)
    monkeypatch.setattr(main_module, "run_risk_stage", fake_run_risk_stage)
    monkeypatch.setattr(main_module, "run_portfolio_stage", fake_run_portfolio_stage)
    monkeypatch.chdir(tmp_path)

    flow = main_module.TradingAgentsFlow(tracing=True)
    result = flow.kickoff(
        inputs={
            "crewai_trigger_payload": {
                "ticker": "nvda",
                "trade_date": "2024-05-24",
                "news_sentiment_block": "news fixture",
                "stocktwits_block": "stocktwits fixture",
                "reddit_block": "reddit fixture",
            }
        }
    )

    assert flow.tracing is True
    assert captured_inputs["ticker"] == "NVDA"
    assert captured_inputs["trade_date"] == "2024-05-24"
    assert captured_inputs["news_sentiment_block"] == "news fixture"
    assert captured_research_inputs == {
        "ticker": "NVDA",
        "trade_date": "2024-05-24",
        **REPORTS,
    }
    assert captured_trader_inputs == {
        "ticker": "NVDA",
        "trade_date": "2024-05-24",
        "investment_plan": RESEARCH_OUTPUTS["investment_plan"],
    }
    assert captured_risk_inputs == {
        "ticker": "NVDA",
        "trade_date": "2024-05-24",
        **REPORTS,
        "trader_plan": TRADER_OUTPUTS["trader_plan"],
    }
    assert captured_portfolio_inputs == {
        "ticker": "NVDA",
        "trade_date": "2024-05-24",
        "investment_plan": RESEARCH_OUTPUTS["investment_plan"],
        "trader_plan": TRADER_OUTPUTS["trader_plan"],
        "risk_debate_history": RISK_OUTPUTS["risk_debate_history"],
    }
    assert result["ticker"] == "NVDA"
    assert result["investment_plan"] == RESEARCH_OUTPUTS["investment_plan"]
    assert result["trader_plan"] == TRADER_OUTPUTS["trader_plan"]
    assert result["risk_debate_history"] == RISK_OUTPUTS["risk_debate_history"]
    assert result["final_trade_decision"] == PORTFOLIO_OUTPUTS["final_trade_decision"]
    assert result["lessons"] == PORTFOLIO_OUTPUTS["lessons"]
    assert result["output_dir"] == "output/NVDA_2024-05-24"

    output_dir = Path("output/NVDA_2024-05-24")
    assert (output_dir / "fundamentals_report.md").read_text() == "fundamentals text"
    assert (output_dir / "sentiment_report.md").read_text() == "sentiment text"
    assert (output_dir / "news_report.md").read_text() == "news text"
    assert (output_dir / "market_report.md").read_text() == "market text"
    assert (output_dir / "debate_history.md").read_text() == RESEARCH_OUTPUTS["debate_history"]
    assert (output_dir / "investment_plan.md").read_text() == (
        "## Recommendation\nBuy\n\n"
        "## Rationale\nresearch rationale\n\n"
        "## Strategic Actions\nincrease exposure\n"
    )
    assert (output_dir / "trader_plan.md").read_text() == (
        "## Action\nBuy\n\n"
        "## Reasoning\nThe research plan supports adding exposure.\n\n"
        "## Entry Price\n102.5\n\n"
        "## Stop Loss\n94.0\n\n"
        "## Position Sizing\n5% of portfolio\n"
    )
    assert (output_dir / "risk_debate_history.md").read_text() == (
        RISK_OUTPUTS["risk_debate_history"]
    )
    assert (output_dir / "final_trade_decision.md").read_text() == (
        "## Rating\nBuy\n\n"
        "## Executive Summary\nEnter on a pullback, size at 5%.\n\n"
        "## Investment Thesis\nThe bull case outweighs the bear case.\n\n"
        "## Price Target\n150.0\n\n"
        "## Time Horizon\n3-6 months\n"
    )


def test_kickoff_uses_default_trading_inputs(monkeypatch, tmp_path):
    captured_inputs = {}

    def fake_run_analyst_stage(inputs):
        captured_inputs.update(inputs)
        return dict(REPORTS)

    def fake_run_research_stage(_inputs):
        return dict(RESEARCH_OUTPUTS)

    def fake_run_trader_stage(_inputs):
        return dict(TRADER_OUTPUTS)

    def fake_run_risk_stage(_inputs):
        return dict(RISK_OUTPUTS)

    def fake_run_portfolio_stage(_inputs):
        return dict(PORTFOLIO_OUTPUTS)

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)
    monkeypatch.setattr(main_module, "run_research_stage", fake_run_research_stage)
    monkeypatch.setattr(main_module, "run_trader_stage", fake_run_trader_stage)
    monkeypatch.setattr(main_module, "run_risk_stage", fake_run_risk_stage)
    monkeypatch.setattr(main_module, "run_portfolio_stage", fake_run_portfolio_stage)
    monkeypatch.chdir(tmp_path)

    result = main_module.kickoff()
    expected_trade_date = datetime.now(UTC).strftime("%Y-%m-%d")

    assert captured_inputs["ticker"] == main_module.DEFAULT_TICKER
    assert captured_inputs["trade_date"] == main_module.DEFAULT_TRADE_DATE
    assert captured_inputs["trade_date"] == expected_trade_date
    assert result["output_dir"] == f"output/NVDA_{expected_trade_date}"




def test_cli_uses_ticker_and_trade_date_payload(monkeypatch):
    captured = {}

    class FakeFlow:
        def __init__(self, tracing):
            captured["tracing"] = tracing

        def kickoff(self, inputs=None):
            captured["inputs"] = inputs
            return {"ok": True}

    monkeypatch.setattr(main_module, "TradingAgentsFlow", FakeFlow)

    result = main_module.cli(["--ticker", "aapl", "--trade-date", "2026-05-25"])

    assert result == {"ok": True}
    assert captured["tracing"] is True
    assert captured["inputs"] == {
        "crewai_trigger_payload": {
            "ticker": "AAPL",
            "trade_date": "2026-05-25",
        }
    }


def test_cli_without_arguments_uses_default_kickoff(monkeypatch):
    calls = []

    def fake_kickoff():
        calls.append("kickoff")
        return {"default": True}

    monkeypatch.setattr(main_module, "kickoff", fake_kickoff)

    result = main_module.cli([])

    assert result == {"default": True}
    assert calls == ["kickoff"]


def test_run_with_trigger_cli_prints_result_and_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        main_module,
        "run_with_trigger",
        lambda: {"final_trade_decision": {"rating": "Overweight"}},
    )

    result = main_module.run_with_trigger_cli()

    assert result is None
    assert '"rating": "Overweight"' in capsys.readouterr().out


def test_invalid_trade_date_stops_before_analyst_stage(monkeypatch):
    called = False

    def fake_run_analyst_stage(_inputs):
        nonlocal called
        called = True
        return dict(REPORTS)

    def fake_run_research_stage(_inputs):
        raise AssertionError("research stage should not run when inputs are invalid")

    def fake_run_trader_stage(_inputs):
        raise AssertionError("trader stage should not run when inputs are invalid")

    def fake_run_risk_stage(_inputs):
        raise AssertionError("risk stage should not run when inputs are invalid")

    def fake_run_portfolio_stage(_inputs):
        raise AssertionError("portfolio stage should not run when inputs are invalid")

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)
    monkeypatch.setattr(main_module, "run_research_stage", fake_run_research_stage)
    monkeypatch.setattr(main_module, "run_trader_stage", fake_run_trader_stage)
    monkeypatch.setattr(main_module, "run_risk_stage", fake_run_risk_stage)
    monkeypatch.setattr(main_module, "run_portfolio_stage", fake_run_portfolio_stage)

    flow = main_module.TradingAgentsFlow(tracing=True)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        flow.kickoff(
            inputs={
                "crewai_trigger_payload": {
                    "ticker": "NVDA",
                    "trade_date": "05/24/2024",
                }
            }
        )

    assert called is False
