#!/usr/bin/env python
from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()
# Enable trace collection for this entry point unless the caller opted out.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "true")

from crewai.flow import Flow, listen, start  # noqa: E402

from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage  # noqa: E402

DEFAULT_TICKER = "NVDA"
DEFAULT_TRADE_DATE = datetime.now(UTC).strftime("%Y-%m-%d")
REPORT_FILES = {
    "fundamentals_report": "fundamentals_report.md",
    "sentiment_report": "sentiment_report.md",
    "news_report": "news_report.md",
    "market_report": "market_report.md",
}


class TradingAgentsState(BaseModel):
    ticker: str = DEFAULT_TICKER
    trade_date: str = DEFAULT_TRADE_DATE
    fundamentals_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    market_report: str = ""
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
    def save_outputs(self, _reports: dict[str, str]) -> dict[str, Any]:
        output_dir = save_analyst_outputs(self.state)
        print(f"Analyst reports saved to {output_dir}")
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


def save_analyst_outputs(state: TradingAgentsState) -> Path:
    output_dir = Path(state.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for attribute, file_name in REPORT_FILES.items():
        report = getattr(state, attribute)
        (output_dir / file_name).write_text(report, encoding="utf-8")

    return output_dir


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
    kickoff()
