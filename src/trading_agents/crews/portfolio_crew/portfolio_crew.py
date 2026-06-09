from __future__ import annotations

from collections.abc import Mapping
import json
import re
from types import SimpleNamespace
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from trading_agents.config import get_settings, resolve_agent_config
from trading_agents.crews.portfolio_crew.lesson_store import (
    LessonStore,
    SeriesFetcher,
    default_fetch_series,
    format_return,
    render_lessons_line,
    resolve_benchmark,
    update_records_with_returns,
)
from trading_agents.schemas import LessonRecord, PortfolioDecision, PortfolioRating


load_dotenv()


PORTFOLIO_TASK_NAMES = ("self_reflection", "final_decision")
PORTFOLIO_TASK_TO_AGENT = {
    "self_reflection": "self_reflection_manager",
    "final_decision": "portfolio_manager",
}
REQUIRED_PORTFOLIO_INPUT_KEYS = (
    "ticker",
    "investment_plan",
    "trader_plan",
    "risk_debate_history",
)


@CrewBase
class PortfolioCrew:
    """TradingAgents portfolio crew.

    A one-person team modeled as two agents: ``portfolio_manager`` makes the
    final decision (deep model) and ``self_reflection_manager`` reflects on
    past decisions whose outcomes are now known (quick model).
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def portfolio_manager(self) -> Agent:
        return Agent(
            config=resolve_agent_config(
                self.agents_config["portfolio_manager"]  # type: ignore[index]
            ),
        )

    @agent
    def self_reflection_manager(self) -> Agent:
        return Agent(
            config=resolve_agent_config(
                self.agents_config["self_reflection_manager"]  # type: ignore[index]
            ),
        )

    @task
    def self_reflection(self) -> Task:
        return Task(
            config=self.tasks_config["self_reflection"],  # type: ignore[index]
        )

    @task
    def final_decision(self) -> Task:
        return Task(
            config=self.tasks_config["final_decision"],  # type: ignore[index]
            output_pydantic=PortfolioDecision,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the portfolio crew."""
        return Crew(
            agents=[
                self.self_reflection_manager(),
                self.portfolio_manager(),
            ],
            tasks=[
                self.self_reflection(),
                self.final_decision(),
            ],
            process=Process.sequential,
            tracing=True,
            verbose=True,
        )


def run_portfolio_stage(
    inputs: Mapping[str, Any],
    *,
    store: LessonStore | None = None,
    fetch_series: SeriesFetcher | None = None,
    max_lessons: int | None = None,
    max_holding_days: int | None = None,
) -> dict[str, Any]:
    """Run the self-reflection process and the final portfolio decision.

    The process, in order: update prior lesson records with realized returns,
    self-reflect on each updated record, retrieve up to ``max_lessons`` records
    as ``{lessons_line}``, make the final decision, then persist a new lesson
    record for this decision.
    """
    prepared = _prepare_portfolio_inputs(inputs)

    settings = get_settings().portfolio_stage
    if max_lessons is None:
        max_lessons = settings.max_lessons
    if store is None:
        store = LessonStore()
    if fetch_series is None:
        fetch_series = default_fetch_series

    ticker = prepared["ticker"]
    trade_date = prepared["trade_date"]
    benchmark_name = resolve_benchmark(ticker)

    # 1. Update existing records with realized returns and holding days.
    book = store.load(ticker)
    updated = update_records_with_returns(
        book.lessons,
        benchmark_name,
        fetch_series,
        max_holding_days=max_holding_days,
    )

    # 2-3. Self-reflect on each just-updated record and write the reflection back.
    for record in updated:
        reflection = _kickoff_portfolio_task(
            "self_reflection",
            {
                "raw_return": format_return(record.raw_return),
                "benchmark_name": benchmark_name,
                "alpha_return": format_return(record.alpha_return),
                "final_decision": record.final_decision,
            },
        )
        record.reflection = str(reflection.raw).strip()
    if updated:
        store.save(ticker, book)

    # 4. Retrieve up to max_lessons records and render {lessons_line}.
    retrieved = list(book.lessons)[-max_lessons:] if max_lessons else []
    lessons_line = render_lessons_line(retrieved)

    # 5. Make the final decision using the upstream artifacts and the lessons.
    decision_result = _kickoff_portfolio_task(
        "final_decision",
        {
            "ticker": ticker,
            "investment_plan": prepared["investment_plan"],
            "trader_plan": prepared["trader_plan"],
            "history": prepared["risk_debate_history"],
            "lessons_line": lessons_line,
        },
    )
    decision = _extract_portfolio_decision(decision_result)

    # Persist a fresh lesson record for this decision (returns filled in later).
    store.append(
        ticker,
        LessonRecord(
            ticker=ticker,
            trade_date=trade_date,
            final_decision=decision.rating.value,
        ),
    )

    return {
        "final_trade_decision": decision.model_dump(),
        "lessons": [record.model_dump() for record in retrieved],
    }


def normalize_rating(value: Any) -> PortfolioRating:
    """Map trivial variants of a rating to the canonical ``PortfolioRating``.

    Behavior (documented and tested):
    - An exact value, optionally with surrounding whitespace or a trailing
      period, normalizes to that rating (``"Buy."`` -> ``Buy``, ``"BUY"`` -> ``Buy``).
    - A string in which exactly one rating keyword appears anywhere normalizes
      to that rating (``"BUY because the thesis is strong"`` -> ``Buy``).
    - Anything ambiguous (two or more distinct rating keywords, such as
      ``"Buy or Sell"``) or unrecognized (``"Maybe later"``) raises a
      ``ValueError``.
    """
    if isinstance(value, PortfolioRating):
        return value

    text = str(value).strip()
    cleaned = text.strip().strip(".").strip()
    for rating in PortfolioRating:
        if cleaned.lower() == rating.value.lower():
            return rating

    words = {word.lower() for word in re.findall(r"[A-Za-z]+", text)}
    present = {
        rating for rating in PortfolioRating if rating.value.lower() in words
    }
    if len(present) == 1:
        return next(iter(present))

    raise ValueError(f"Ambiguous or unrecognized portfolio rating: {value!r}")


def _extract_portfolio_decision(result: SimpleNamespace) -> PortfolioDecision:
    pydantic_output = getattr(result, "pydantic", None)
    if isinstance(pydantic_output, PortfolioDecision):
        return pydantic_output
    if pydantic_output is not None and hasattr(pydantic_output, "model_dump"):
        data = dict(pydantic_output.model_dump())
        if "rating" in data:
            data["rating"] = normalize_rating(data["rating"]).value
        return PortfolioDecision.model_validate(data)

    raw = str(getattr(result, "raw", None) or "")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            "Portfolio crew output was not valid PortfolioDecision JSON."
        ) from exc
    if not isinstance(data, Mapping):
        raise ValueError("Portfolio crew output was not a JSON object.")
    data = dict(data)
    if "rating" in data:
        data["rating"] = normalize_rating(data["rating"]).value
    return PortfolioDecision.model_validate(data)


def _kickoff_portfolio_task(task_name: str, inputs: Mapping[str, Any]) -> SimpleNamespace:
    if task_name not in PORTFOLIO_TASK_TO_AGENT:
        raise ValueError(f"Unknown portfolio task: {task_name}")

    source = PortfolioCrew()
    task_obj = getattr(source, task_name)()
    agent_obj = getattr(source, PORTFOLIO_TASK_TO_AGENT[task_name])()
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


def _prepare_portfolio_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    missing = [
        key for key in REQUIRED_PORTFOLIO_INPUT_KEYS if _is_blank(inputs.get(key))
    ]
    if missing:
        raise ValueError(
            "Portfolio stage inputs missing required fields: " + ", ".join(missing)
        )

    prepared = dict(inputs)
    prepared["ticker"] = str(inputs["ticker"]).strip()
    prepared["trade_date"] = str(
        inputs.get("trade_date") or inputs.get("current_date") or ""
    ).strip()
    prepared["investment_plan"] = _format_plan(inputs["investment_plan"])
    prepared["trader_plan"] = _format_plan(inputs["trader_plan"])
    prepared["risk_debate_history"] = str(inputs["risk_debate_history"]).strip()
    return prepared


def _format_plan(plan: Any) -> str:
    if isinstance(plan, str):
        return plan.strip()
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()
    if isinstance(plan, Mapping):
        return json.dumps(dict(plan), indent=2, sort_keys=True)
    return str(plan).strip()


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""
