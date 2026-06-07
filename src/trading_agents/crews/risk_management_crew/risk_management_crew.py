from __future__ import annotations

from collections.abc import Mapping
import json
from types import SimpleNamespace
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from trading_agents.config import get_settings, resolve_agent_config


load_dotenv()


RISK_TASK_NAMES = (
    "aggressive_risk_analysis",
    "conservative_risk_analysis",
    "neutral_risk_analysis",
)
RISK_TASK_TO_AGENT = {
    "aggressive_risk_analysis": "aggressive_analyst",
    "conservative_risk_analysis": "conservative_analyst",
    "neutral_risk_analysis": "neutral_analyst",
}
RISK_TASK_TO_SPEAKER = {
    "aggressive_risk_analysis": "Aggressive Analyst",
    "conservative_risk_analysis": "Conservative Analyst",
    "neutral_risk_analysis": "Neutral Analyst",
}
REQUIRED_RISK_INPUT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "trader_plan",
)


@CrewBase
class RiskManagementCrew:
    """TradingAgents risk management crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def aggressive_analyst(self) -> Agent:
        return Agent(
            config=resolve_agent_config(
                self.agents_config["aggressive_analyst"]  # type: ignore[index]
            ),
        )

    @agent
    def conservative_analyst(self) -> Agent:
        return Agent(
            config=resolve_agent_config(
                self.agents_config["conservative_analyst"]  # type: ignore[index]
            ),
        )

    @agent
    def neutral_analyst(self) -> Agent:
        return Agent(
            config=resolve_agent_config(
                self.agents_config["neutral_analyst"]  # type: ignore[index]
            ),
        )

    @task
    def aggressive_risk_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["aggressive_risk_analysis"],  # type: ignore[index]
        )

    @task
    def conservative_risk_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["conservative_risk_analysis"],  # type: ignore[index]
        )

    @task
    def neutral_risk_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["neutral_risk_analysis"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the risk management crew."""
        return Crew(
            agents=[
                self.aggressive_analyst(),
                self.conservative_analyst(),
                self.neutral_analyst(),
            ],
            tasks=[
                self.aggressive_risk_analysis(),
                self.conservative_risk_analysis(),
                self.neutral_risk_analysis(),
            ],
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_risk_stage(
    inputs: Mapping[str, Any],
    max_rounds: int | None = None,
) -> dict[str, str]:
    """Run the risk debate and return the ordered debate transcript."""
    if max_rounds is None:
        max_rounds = get_settings().risk_stage.max_rounds
    if max_rounds < 1:
        raise ValueError("Risk stage max_rounds must be at least 1.")

    prepared_inputs = _prepare_risk_inputs(inputs)
    debate_entries: list[str] = []
    current_aggressive_response = ""
    current_conservative_response = ""
    current_neutral_response = ""

    for _ in range(max_rounds):
        aggressive_result = _kickoff_risk_task(
            "aggressive_risk_analysis",
            {
                **prepared_inputs,
                "history": _format_debate_history(debate_entries),
                "current_conservative_response": current_conservative_response,
                "current_neutral_response": current_neutral_response,
            },
        )
        current_aggressive_response = _format_turn(
            RISK_TASK_TO_SPEAKER["aggressive_risk_analysis"],
            aggressive_result.raw,
        )
        debate_entries.append(current_aggressive_response)

        conservative_result = _kickoff_risk_task(
            "conservative_risk_analysis",
            {
                **prepared_inputs,
                "history": _format_debate_history(debate_entries),
                "current_aggressive_response": current_aggressive_response,
                "current_neutral_response": current_neutral_response,
            },
        )
        current_conservative_response = _format_turn(
            RISK_TASK_TO_SPEAKER["conservative_risk_analysis"],
            conservative_result.raw,
        )
        debate_entries.append(current_conservative_response)

        neutral_result = _kickoff_risk_task(
            "neutral_risk_analysis",
            {
                **prepared_inputs,
                "history": _format_debate_history(debate_entries),
                "current_aggressive_response": current_aggressive_response,
                "current_conservative_response": current_conservative_response,
            },
        )
        current_neutral_response = _format_turn(
            RISK_TASK_TO_SPEAKER["neutral_risk_analysis"],
            neutral_result.raw,
        )
        debate_entries.append(current_neutral_response)

    return {"risk_debate_history": _format_debate_history(debate_entries)}


def _prepare_risk_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_RISK_INPUT_KEYS if _is_blank(inputs.get(key))]
    if missing:
        raise ValueError(
            "Risk stage inputs missing required fields: " + ", ".join(missing)
        )

    prepared = dict(inputs)
    ticker = str(inputs.get("ticker") or "UNKNOWN").strip()
    prepared["ticker"] = ticker
    prepared["trade_date"] = str(
        inputs.get("trade_date") or inputs.get("current_date") or ""
    ).strip()
    prepared["market_research_report"] = str(inputs["market_report"]).strip()
    prepared["trader_plan"] = _format_trader_plan(inputs["trader_plan"])
    return prepared


def _kickoff_risk_task(task_name: str, inputs: Mapping[str, Any]) -> SimpleNamespace:
    if task_name not in RISK_TASK_TO_AGENT:
        raise ValueError(f"Unknown risk task: {task_name}")

    source = RiskManagementCrew()
    task_obj = getattr(source, task_name)()
    agent_obj = getattr(source, RISK_TASK_TO_AGENT[task_name])()
    result = Crew(
        agents=[agent_obj],
        tasks=[task_obj],
        process=Process.sequential,
        tracing=True,
        verbose=True,
    ).kickoff(inputs=dict(inputs))

    task_outputs = list(getattr(result, "tasks_output", []) or [])
    task_output = task_outputs[0] if task_outputs else None
    raw = str(
        getattr(task_output, "raw", None) or getattr(result, "raw", None) or ""
    )
    pydantic_output = getattr(task_output, "pydantic", None) or getattr(
        result,
        "pydantic",
        None,
    )
    return SimpleNamespace(raw=raw, pydantic=pydantic_output)


def _format_turn(speaker: str, raw: str) -> str:
    cleaned = str(raw).strip()
    return f"{speaker}: {cleaned}"


def _format_debate_history(entries: list[str]) -> str:
    return "\n\n".join(entries)


def _format_trader_plan(trader_plan: Any) -> str:
    if isinstance(trader_plan, str):
        return trader_plan.strip()
    if hasattr(trader_plan, "model_dump"):
        trader_plan = trader_plan.model_dump()
    if isinstance(trader_plan, Mapping):
        return json.dumps(dict(trader_plan), indent=2, sort_keys=True)
    return str(trader_plan).strip()


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""
