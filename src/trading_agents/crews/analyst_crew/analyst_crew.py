from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.crews.crew_output import CrewOutput
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from trading_agents.config import (
    get_settings,
    resolve_agent_config,
    resolve_analyst_runtime_config,
)
from trading_agents.tools import (
    fetch_reddit_posts,
    fetch_stocktwits_messages,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_news,
    get_stock_data,
)


load_dotenv()


REPORT_TASK_TO_KEY = {
    "market_analysis": "market_report",
    "sentiment_analysis": "sentiment_report",
    "news_analysis": "news_report",
    "fundamentals_analysis": "fundamentals_report",
}
ANALYST_TASK_NAMES = tuple(REPORT_TASK_TO_KEY)


@CrewBase
class AnalystCrew:
    """TradingAgents analyst crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def analyst(self) -> Agent:
        return Agent(
            config=resolve_agent_config(self.agents_config["analyst"]),  # type: ignore[index]
        )

    @task
    def market_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["market_analysis"],  # type: ignore[index]
            tools=[get_stock_data, get_indicators],
        )

    @task
    def sentiment_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["sentiment_analysis"],  # type: ignore[index]
            tools=[],
        )

    @task
    def news_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["news_analysis"],  # type: ignore[index]
            tools=[get_news, get_global_news],
        )

    @task
    def fundamentals_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["fundamentals_analysis"],  # type: ignore[index]
            tools=[
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the analyst crew."""
        return Crew(
            agents=[self.analyst()],
            tasks=[
                self.market_analysis(),
                self.sentiment_analysis(),
                self.news_analysis(),
                self.fundamentals_analysis(),
            ],
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_analyst_stage(inputs: Mapping[str, Any]) -> dict[str, str]:
    """Run the analyst stage sequentially and return all reports by stable key."""
    prepared_inputs = prepare_analyst_inputs(inputs)
    result = AnalystCrew().crew().kickoff(inputs=prepared_inputs)
    return extract_analyst_reports(result)


def prepare_analyst_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize analyst-stage inputs and prefetch prompt-only evidence blocks."""
    ticker = _required_string(inputs, "ticker").upper()
    current_date = _current_date(inputs)
    runtime = resolve_analyst_runtime_config(inputs)
    settings = get_settings()
    start_date = _days_back(current_date, days=runtime.lookback_days)

    prepared = dict(inputs)
    prepared["ticker"] = ticker
    prepared["trade_date"] = current_date
    prepared["current_date"] = current_date
    prepared["start_date"] = start_date
    prepared["end_date"] = current_date
    prepared["sentiment_start_date"] = start_date
    prepared["asset_label"] = str(inputs.get("asset_label") or ticker)

    if "news_block" in prepared and "news_sentiment_block" not in prepared:
        prepared["news_sentiment_block"] = prepared["news_block"]
    if "news_sentiment_block" not in prepared:
        prepared["news_sentiment_block"] = get_news._run(
            ticker,
            start_date,
            current_date,
            limit=runtime.news_limit,
        )
    if "news_block" not in prepared:
        prepared["news_block"] = prepared["news_sentiment_block"]

    if "stocktwits_block" not in prepared:
        prepared["stocktwits_block"] = fetch_stocktwits_messages(
            ticker,
            limit=runtime.stocktwits_limit,
            timeout=settings.sentiment.stocktwits_timeout,
        )
    if "reddit_block" not in prepared:
        prepared["reddit_block"] = fetch_reddit_posts(
            ticker,
            limit_per_sub=runtime.reddit_limit_per_sub,
            timeout=runtime.reddit_timeout,
        )
    return prepared


def extract_analyst_reports(result: CrewOutput) -> dict[str, str]:
    """Extract analyst reports from a CrewAI result without relying on raw."""
    task_outputs = list(getattr(result, "tasks_output", []) or [])
    reports: dict[str, str] = {}
    task_names = list(REPORT_TASK_TO_KEY)

    for index, task_output in enumerate(task_outputs):
        task_name = getattr(task_output, "name", None)
        report_key = REPORT_TASK_TO_KEY.get(task_name)
        if report_key is None and index < len(task_names):
            report_key = REPORT_TASK_TO_KEY[task_names[index]]
        if report_key:
            reports[report_key] = str(getattr(task_output, "raw", "") or "")

    ordered_report_keys = list(REPORT_TASK_TO_KEY.values())
    missing = [
        report_key for report_key in ordered_report_keys if report_key not in reports
    ]
    if missing:
        raise ValueError(f"Analyst crew output missing reports: {', '.join(missing)}")

    return {report_key: reports[report_key] for report_key in ordered_report_keys}


def _current_date(inputs: Mapping[str, Any]) -> str:
    value = inputs.get("current_date") or inputs.get("trade_date")
    if value is None or str(value).strip() == "":
        raise ValueError(
            "Analyst stage input 'current_date' or 'trade_date' is required."
        )
    current_date = str(value).strip()
    _parse_yyyy_mm_dd(current_date)
    return current_date


def _required_string(inputs: Mapping[str, Any], key: str) -> str:
    value = inputs.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Analyst stage input '{key}' is required.")
    return str(value).strip()


def _days_back(current_date: str, days: int) -> str:
    return (_parse_yyyy_mm_dd(current_date) - timedelta(days=days)).strftime("%Y-%m-%d")


def _parse_yyyy_mm_dd(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")
