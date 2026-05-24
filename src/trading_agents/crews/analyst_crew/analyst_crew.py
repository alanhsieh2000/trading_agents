from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.crews.crew_output import CrewOutput
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

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
    "fundamentals_analysis": "fundamentals_report",
    "sentiment_analysis": "sentiment_report",
    "news_analysis": "news_report",
    "market_analysis": "market_report",
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
    def fundamentals_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["fundamentals_analyst"],  # type: ignore[index]
            tools=[
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ],
        )

    @agent
    def sentiment_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["sentiment_analyst"],  # type: ignore[index]
            tools=[],
        )

    @agent
    def news_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["news_analyst"],  # type: ignore[index]
            tools=[get_news, get_global_news],
        )

    @agent
    def market_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["market_analyst"],  # type: ignore[index]
            tools=[get_stock_data, get_indicators],
        )

    @task
    def fundamentals_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["fundamentals_analysis"],  # type: ignore[index]
        )

    @task
    def sentiment_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["sentiment_analysis"],  # type: ignore[index]
        )

    @task
    def news_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["news_analysis"],  # type: ignore[index]
        )

    @task
    def market_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["market_analysis"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the analyst crew."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_analyst_stage(inputs: Mapping[str, Any]) -> dict[str, str]:
    """Run the analyst stage in parallel and return all reports by stable key."""
    prepared_inputs = prepare_analyst_inputs(inputs)
    task_outputs = run_parallel_analyst_tasks(prepared_inputs)
    result = CrewOutput(raw=task_outputs[-1].raw, tasks_output=task_outputs)
    return extract_analyst_reports(result)


def run_parallel_analyst_tasks(inputs: Mapping[str, Any]):
    """Execute the four independent analyst tasks concurrently."""
    with ThreadPoolExecutor(max_workers=len(ANALYST_TASK_NAMES)) as executor:
        return list(
            executor.map(
                lambda task_name: _run_single_analyst_task(task_name, inputs),
                ANALYST_TASK_NAMES,
            )
        )


def _run_single_analyst_task(task_name: str, inputs: Mapping[str, Any]):
    crew_source = AnalystCrew()
    task_instance = getattr(crew_source, task_name)()
    if task_instance.agent is None:
        raise ValueError(f"Analyst task {task_name!r} has no agent assigned.")

    result = Crew(
        agents=[task_instance.agent],
        tasks=[task_instance],
        process=Process.sequential,
        tracing=True,
        verbose=True,
    ).kickoff(inputs=dict(inputs))
    if not result.tasks_output:
        raise ValueError(f"Analyst task {task_name!r} produced no output.")
    return result.tasks_output[0]


def prepare_analyst_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize analyst-stage inputs and prefetch sentiment prompt blocks."""
    ticker = _required_string(inputs, "ticker").upper()
    trade_date = _required_string(inputs, "trade_date")
    start_date = str(inputs.get("sentiment_start_date") or _seven_days_back(trade_date))

    prepared = dict(inputs)
    prepared["ticker"] = ticker
    prepared["trade_date"] = trade_date
    prepared["sentiment_start_date"] = start_date
    if "news_sentiment_block" not in prepared:
        prepared["news_sentiment_block"] = get_news._run(
            ticker, start_date, trade_date, limit=10
        )
    if "stocktwits_block" not in prepared:
        prepared["stocktwits_block"] = fetch_stocktwits_messages(ticker, limit=30)
    if "reddit_block" not in prepared:
        prepared["reddit_block"] = fetch_reddit_posts(ticker)
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
    missing = [report_key for report_key in ordered_report_keys if report_key not in reports]
    if missing:
        raise ValueError(f"Analyst crew output missing reports: {', '.join(missing)}")

    return {report_key: reports[report_key] for report_key in ordered_report_keys}


def _required_string(inputs: Mapping[str, Any], key: str) -> str:
    value = inputs.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Analyst stage input '{key}' is required.")
    return str(value).strip()


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )
