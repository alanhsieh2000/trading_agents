#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()
# Enable trace collection for this entry point unless the caller opted out.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "true")

from crewai.flow import Flow, listen, start  # noqa: E402

from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage  # noqa: E402
from trading_agents.crews.research_crew.research_crew import run_research_stage  # noqa: E402
from trading_agents.crews.risk_management_crew.risk_management_crew import (  # noqa: E402
    run_risk_stage,
)
from trading_agents.crews.trader_crew.trader_crew import run_trader_stage  # noqa: E402

DEFAULT_TICKER = "NVDA"
DEFAULT_TRADE_DATE = datetime.now(UTC).strftime("%Y-%m-%d")
REPORT_FILES = {
    "fundamentals_report": "fundamentals_report.md",
    "sentiment_report": "sentiment_report.md",
    "news_report": "news_report.md",
    "market_report": "market_report.md",
}
RESEARCH_OUTPUT_FILES = {
    "debate_history": "debate_history.md",
    "investment_plan": "investment_plan.md",
}
TRADER_OUTPUT_FILES = {
    "trader_plan": "trader_plan.md",
}
RISK_OUTPUT_FILES = {
    "risk_debate_history": "risk_debate_history.md",
}


class TradingAgentsState(BaseModel):
    ticker: str = DEFAULT_TICKER
    trade_date: str = DEFAULT_TRADE_DATE
    fundamentals_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    market_report: str = ""
    debate_history: str = ""
    investment_plan: dict[str, Any] = Field(default_factory=dict)
    trader_plan: dict[str, Any] = Field(default_factory=dict)
    risk_debate_history: str = ""
    output_dir: str = ""


class TradingAgentsFlow(Flow[TradingAgentsState]):
    @start()
    def prepare_inputs(
        self, crewai_trigger_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = _normalize_payload(crewai_trigger_payload)
        ticker = str(payload.get("ticker") or self.state.ticker).strip().upper()
        trade_date = str(payload.get("trade_date") or self.state.trade_date).strip()

        _validate_ticker(ticker)
        _validate_trade_date(trade_date)

        self.state.ticker = ticker
        self.state.trade_date = trade_date
        self.state.output_dir = str(Path("output") / f"{ticker}_{trade_date}")

        stage_inputs = dict(payload)
        stage_inputs["ticker"] = ticker
        stage_inputs["trade_date"] = trade_date

        print(f"Prepared analyst stage for {ticker} on {trade_date}")
        return stage_inputs

    @listen(prepare_inputs)
    def run_analysts(self, inputs: dict[str, Any]) -> dict[str, str]:
        print(f"Running analyst stage for {self.state.ticker} on {self.state.trade_date}")
        reports = run_analyst_stage(inputs)

        self.state.fundamentals_report = reports["fundamentals_report"]
        self.state.sentiment_report = reports["sentiment_report"]
        self.state.news_report = reports["news_report"]
        self.state.market_report = reports["market_report"]

        print("Analyst stage complete")
        return reports

    @listen(run_analysts)
    def run_research(self, reports: dict[str, str]) -> dict[str, Any]:
        print(f"Running research stage for {self.state.ticker} on {self.state.trade_date}")
        research_inputs: dict[str, Any] = {
            "ticker": self.state.ticker,
            "trade_date": self.state.trade_date,
            **reports,
        }
        research_outputs = run_research_stage(research_inputs)

        self.state.debate_history = str(research_outputs["debate_history"])
        self.state.investment_plan = dict(research_outputs["investment_plan"])

        print("Research stage complete")
        return research_outputs

    @listen(run_research)
    def run_trader(self, research_outputs: dict[str, Any]) -> dict[str, Any]:
        print(f"Running trader stage for {self.state.ticker} on {self.state.trade_date}")
        trader_inputs: dict[str, Any] = {
            "ticker": self.state.ticker,
            "trade_date": self.state.trade_date,
            "investment_plan": research_outputs["investment_plan"],
        }
        trader_outputs = run_trader_stage(trader_inputs)
        trader_plan = trader_outputs["trader_plan"]
        if hasattr(trader_plan, "model_dump"):
            self.state.trader_plan = trader_plan.model_dump()
        else:
            self.state.trader_plan = dict(trader_plan)

        print("Trader stage complete")
        return trader_outputs

    @listen(run_trader)
    def run_risk_management(self, trader_outputs: dict[str, Any]) -> dict[str, str]:
        print(f"Running risk stage for {self.state.ticker} on {self.state.trade_date}")
        trader_plan = trader_outputs["trader_plan"]
        risk_inputs: dict[str, Any] = {
            "ticker": self.state.ticker,
            "trade_date": self.state.trade_date,
            "fundamentals_report": self.state.fundamentals_report,
            "sentiment_report": self.state.sentiment_report,
            "news_report": self.state.news_report,
            "market_report": self.state.market_report,
            "trader_plan": trader_plan,
        }
        risk_outputs = run_risk_stage(risk_inputs)
        self.state.risk_debate_history = str(risk_outputs["risk_debate_history"])

        print("Risk stage complete")
        return risk_outputs

    @listen(run_risk_management)
    def save_outputs(self, _risk_outputs: dict[str, Any]) -> dict[str, Any]:
        output_dir = save_outputs(self.state)
        print(f"TradingAgents outputs saved to {output_dir}")
        return self.state.model_dump()


def kickoff() -> Any:
    flow = TradingAgentsFlow(tracing=True)
    return flow.kickoff()


def plot() -> None:
    flow = TradingAgentsFlow(tracing=True)
    flow.plot()


def run_with_trigger() -> Any:
    import json
    import sys

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        raise Exception("Invalid JSON payload provided as argument") from exc

    flow = TradingAgentsFlow(tracing=True)
    try:
        return flow.kickoff(inputs={"crewai_trigger_payload": trigger_payload})
    except Exception as exc:
        raise Exception(f"An error occurred while running the flow with trigger: {exc}") from exc



def cli(argv: list[str] | None = None) -> Any:
    parser = argparse.ArgumentParser(
        description=(
            "Run the TradingAgents analyst flow and save reports under output/<ticker>_<trade_date>."
        )
    )
    parser.add_argument("--ticker", help="Ticker symbol to analyze, for example AAPL or NVDA.")
    parser.add_argument(
        "--trade-date",
        help="Trade date in YYYY-MM-DD format. Defaults to the current UTC date.",
    )
    args = parser.parse_args(argv)

    payload: dict[str, str] = {}
    if args.ticker:
        payload["ticker"] = args.ticker.strip().upper()
    if args.trade_date:
        payload["trade_date"] = args.trade_date.strip()

    if not payload:
        return kickoff()

    flow = TradingAgentsFlow(tracing=True)
    return flow.kickoff(inputs={"crewai_trigger_payload": payload})

def save_outputs(state: TradingAgentsState) -> Path:
    output_dir = Path(state.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_analyst_outputs(state, output_dir)

    (output_dir / RESEARCH_OUTPUT_FILES["debate_history"]).write_text(
        state.debate_history,
        encoding="utf-8",
    )
    (output_dir / RESEARCH_OUTPUT_FILES["investment_plan"]).write_text(
        _format_investment_plan(state.investment_plan),
        encoding="utf-8",
    )
    (output_dir / TRADER_OUTPUT_FILES["trader_plan"]).write_text(
        _format_trader_plan(state.trader_plan),
        encoding="utf-8",
    )
    (output_dir / RISK_OUTPUT_FILES["risk_debate_history"]).write_text(
        state.risk_debate_history,
        encoding="utf-8",
    )

    return output_dir


def save_analyst_outputs(state: TradingAgentsState) -> Path:
    output_dir = Path(state.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_analyst_outputs(state, output_dir)
    return output_dir


def _write_analyst_outputs(state: TradingAgentsState, output_dir: Path) -> None:
    for attribute, file_name in REPORT_FILES.items():
        report = getattr(state, attribute)
        (output_dir / file_name).write_text(report, encoding="utf-8")


def _format_investment_plan(investment_plan: dict[str, Any]) -> str:
    if not investment_plan:
        return ""

    sections = [
        ("Recommendation", investment_plan.get("recommendation", "")),
        ("Rationale", investment_plan.get("rationale", "")),
        ("Strategic Actions", investment_plan.get("strategic_actions", "")),
    ]
    return "\n\n".join(f"## {title}\n{value}".rstrip() for title, value in sections) + "\n"


def _format_trader_plan(trader_plan: dict[str, Any]) -> str:
    if not trader_plan:
        return ""

    sections = [
        ("Action", trader_plan.get("action", "")),
        ("Reasoning", trader_plan.get("reasoning", "")),
        ("Entry Price", trader_plan.get("entry_price", "")),
        ("Stop Loss", trader_plan.get("stop_loss", "")),
        ("Position Sizing", trader_plan.get("position_sizing", "")),
    ]
    return "\n\n".join(f"## {title}\n{value}".rstrip() for title, value in sections) + "\n"


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("crewai_trigger_payload must be a JSON object.")
    return payload


def _validate_ticker(ticker: str) -> None:
    if ticker == "":
        raise ValueError("ticker is required.")


def _validate_trade_date(trade_date: str) -> None:
    try:
        datetime.strptime(trade_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("trade_date must use YYYY-MM-DD format.") from exc


if __name__ == "__main__":
    cli()
