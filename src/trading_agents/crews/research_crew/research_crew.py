from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
import re

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, task, crew
from dotenv import load_dotenv

from trading_agents.schemas import InvestmentPlan


load_dotenv()


RESEARCH_TASK_NAMES = ("bull_research", "bear_research", "research_management")
RESEARCH_TASK_TO_AGENT = {
    "bull_research": "bull_researcher",
    "bear_research": "bear_researcher",
    "research_management": "research_manager",
}
REQUIRED_REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
)
HAS_MORE_PATTERN = re.compile(r"^HAS_MORE:\s*(yes|no)\s*$", re.IGNORECASE | re.MULTILINE)


@CrewBase
class ResearchCrew:
    """TradingAgents research crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def bull_researcher(self) -> Agent:
        return Agent(config=self.agents_config["bull_researcher"])  # type: ignore[index]

    @agent
    def bear_researcher(self) -> Agent:
        return Agent(config=self.agents_config["bear_researcher"])  # type: ignore[index]

    @agent
    def research_manager(self) -> Agent:
        return Agent(config=self.agents_config["research_manager"])  # type: ignore[index]

    @task
    def bull_research(self) -> Task:
        return Task(
            config=self.tasks_config["bull_research"],  # type: ignore[index]
        )

    @task
    def bear_research(self) -> Task:
        return Task(
            config=self.tasks_config["bear_research"],  # type: ignore[index]
        )

    @task
    def research_management(self) -> Task:
        return Task(
            config=self.tasks_config["research_management"],  # type: ignore[index]
            output_pydantic=InvestmentPlan,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the research crew."""
        return Crew(
            agents=[
                self.bull_researcher(),
                self.bear_researcher(),
                self.research_manager(),
            ],
            tasks=[
                self.bull_research(),
                self.bear_research(),
                self.research_management(),
            ],
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_research_stage(
    inputs: Mapping[str, Any],
    max_rounds: int = 2,
) -> dict[str, Any]:
    if max_rounds < 1:
        raise ValueError("Research stage max_rounds must be at least 1.")

    prepared_inputs = _prepare_research_inputs(inputs)
    debate_entries: list[str] = []
    investment_plan: dict[str, Any] | None = None

    for _ in range(max_rounds):
        round_has_more: list[bool] = []
        debate_history = _format_debate_history(debate_entries)

        bull_result = _kickoff_research_task(
            "bull_research",
            {**prepared_inputs, "debate_history": debate_history},
        )
        debate_entries.append(_format_turn("bull_research", bull_result.raw))
        round_has_more.append(_has_more(bull_result.raw))

        debate_history = _format_debate_history(debate_entries)
        bear_result = _kickoff_research_task(
            "bear_research",
            {**prepared_inputs, "debate_history": debate_history},
        )
        debate_entries.append(_format_turn("bear_research", bear_result.raw))
        round_has_more.append(_has_more(bear_result.raw))

        debate_history = _format_debate_history(debate_entries)
        manager_result = _kickoff_research_task(
            "research_management",
            {**prepared_inputs, "debate_history": debate_history},
        )
        investment_plan = _serialize_investment_plan(manager_result)

        if not any(round_has_more):
            break

    if investment_plan is None:
        raise ValueError("Research stage did not produce an investment plan.")

    return {
        "debate_history": _format_debate_history(debate_entries),
        "investment_plan": investment_plan,
    }


def _prepare_research_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_REPORT_KEYS if _is_blank(inputs.get(key))]
    if missing:
        raise ValueError(
            "Research stage inputs missing required analyst reports: "
            + ", ".join(missing)
        )
    prepared = dict(inputs)
    prepared["ticker"] = str(inputs.get("ticker") or "UNKNOWN").strip().upper()
    prepared["trade_date"] = str(
        inputs.get("trade_date") or inputs.get("current_date") or ""
    ).strip()
    return prepared


def _kickoff_research_task(task_name: str, inputs: Mapping[str, Any]) -> SimpleNamespace:
    if task_name not in RESEARCH_TASK_TO_AGENT:
        raise ValueError(f"Unknown research task: {task_name}")

    source = ResearchCrew()
    task_obj = getattr(source, task_name)()
    agent_obj = getattr(source, RESEARCH_TASK_TO_AGENT[task_name])()
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
        getattr(task_output, "raw", None)
        or getattr(result, "raw", None)
        or ""
    )
    pydantic_output = getattr(task_output, "pydantic", None) or getattr(
        result, "pydantic", None
    )
    return SimpleNamespace(raw=raw, pydantic=pydantic_output)


def _serialize_investment_plan(result: SimpleNamespace) -> dict[str, Any]:
    pydantic_output = getattr(result, "pydantic", None)
    if isinstance(pydantic_output, InvestmentPlan):
        return pydantic_output.model_dump()
    if pydantic_output is not None and hasattr(pydantic_output, "model_dump"):
        return pydantic_output.model_dump()
    try:
        return InvestmentPlan.model_validate_json(str(result.raw)).model_dump()
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise ValueError("Research manager output did not match InvestmentPlan.") from exc


def _format_turn(task_name: str, raw: str) -> str:
    cleaned = str(raw).strip()
    return f"## {task_name}\n{cleaned}"


def _format_debate_history(entries: list[str]) -> str:
    return "\n\n".join(entries)


def _has_more(raw: str) -> bool:
    match = HAS_MORE_PATTERN.search(str(raw))
    if match is None:
        return True
    return match.group(1).lower() == "yes"


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""
