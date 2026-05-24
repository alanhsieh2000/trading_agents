from pathlib import Path

import pytest

from trading_agents import main as main_module


REPORTS = {
    "fundamentals_report": "fundamentals text",
    "sentiment_report": "sentiment text",
    "news_report": "news text",
    "market_report": "market text",
}


def test_trading_agents_flow_runs_analyst_stage_with_trigger(monkeypatch, tmp_path):
    captured_inputs = {}

    def fake_run_analyst_stage(inputs):
        captured_inputs.update(inputs)
        return dict(REPORTS)

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)
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
    assert result["ticker"] == "NVDA"
    assert result["output_dir"] == "output/NVDA_2024-05-24"

    output_dir = Path("output/NVDA_2024-05-24")
    assert (output_dir / "fundamentals_report.md").read_text() == "fundamentals text"
    assert (output_dir / "sentiment_report.md").read_text() == "sentiment text"
    assert (output_dir / "news_report.md").read_text() == "news text"
    assert (output_dir / "market_report.md").read_text() == "market text"


def test_kickoff_uses_default_trading_inputs(monkeypatch, tmp_path):
    captured_inputs = {}

    def fake_run_analyst_stage(inputs):
        captured_inputs.update(inputs)
        return dict(REPORTS)

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)
    monkeypatch.chdir(tmp_path)

    result = main_module.kickoff()

    assert captured_inputs["ticker"] == main_module.DEFAULT_TICKER
    assert captured_inputs["trade_date"] == main_module.DEFAULT_TRADE_DATE
    assert result["output_dir"] == "output/NVDA_2024-05-24"


def test_invalid_trade_date_stops_before_analyst_stage(monkeypatch):
    called = False

    def fake_run_analyst_stage(_inputs):
        nonlocal called
        called = True
        return dict(REPORTS)

    monkeypatch.setattr(main_module, "run_analyst_stage", fake_run_analyst_stage)

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
