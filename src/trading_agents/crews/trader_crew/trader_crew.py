from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.crews.crew_output import CrewOutput
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from trading_agents.config import resolve_agent_config
from trading_agents.schemas import TraderProposal


load_dotenv()


@CrewBase
class TraderCrew:
    """TradingAgents trader crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def trader_agent(self) -> Agent:
        return Agent(
            config=resolve_agent_config(self.agents_config["trader_agent"]),  # type: ignore[index]
        )

    @task
    def trader_decision(self) -> Task:
        return Task(
            config=self.tasks_config["trader_decision"],  # type: ignore[index]
            output_pydantic=TraderProposal,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the trader crew."""
        return Crew(
            agents=[self.trader_agent()],
            tasks=[self.trader_decision()],
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_trader_stage(inputs: Mapping[str, Any]) -> dict[str, TraderProposal]:
    """Run the trader stage once and return its structured proposal."""
    prepared_inputs = _prepare_trader_inputs(inputs)
    result = TraderCrew().crew().kickoff(inputs=prepared_inputs)
    return {"trader_plan": _extract_trader_plan(result)}


def _prepare_trader_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _required_string(inputs, "ticker")
    investment_plan = inputs.get("investment_plan")
    if _is_blank(investment_plan):
        raise ValueError("Trader stage input 'investment_plan' is required.")

    prepared = dict(inputs)
    prepared["ticker"] = ticker
    prepared["investment_plan"] = _format_investment_plan(investment_plan)
    prepared["trade_date"] = str(inputs.get("trade_date") or "").strip()
    return prepared


def _extract_trader_plan(result: CrewOutput) -> TraderProposal:
    task_outputs = list(getattr(result, "tasks_output", []) or [])
    candidates = [
        getattr(task_outputs[0], "pydantic", None) if task_outputs else None,
        getattr(result, "pydantic", None),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, TraderProposal):
            return candidate
        if hasattr(candidate, "model_dump"):
            return TraderProposal.model_validate(candidate.model_dump())
        return TraderProposal.model_validate(candidate)

    task_raw = getattr(task_outputs[0], "raw", None) if task_outputs else None
    raw = str(task_raw or getattr(result, "raw", None) or "")
    try:
        return TraderProposal.model_validate_json(raw)
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise ValueError("Trader crew output did not match TraderProposal.") from exc


def _format_investment_plan(investment_plan: Any) -> str:
    if isinstance(investment_plan, str):
        return investment_plan.strip()
    if hasattr(investment_plan, "model_dump"):
        investment_plan = investment_plan.model_dump()
    if isinstance(investment_plan, Mapping):
        return json.dumps(dict(investment_plan), indent=2, sort_keys=True)
    return str(investment_plan).strip()


def _required_string(inputs: Mapping[str, Any], key: str) -> str:
    value = inputs.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Trader stage input '{key}' is required.")
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""
