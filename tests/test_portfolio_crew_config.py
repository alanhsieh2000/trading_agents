from crewai import Process
import yaml

from trading_agents.config import get_settings
from trading_agents.crews.portfolio_crew import portfolio_crew as portfolio_module
from trading_agents.crews.portfolio_crew.portfolio_crew import PortfolioCrew


AGENT_KEYS = {"portfolio_manager", "self_reflection_manager"}
TASK_KEYS = ("self_reflection", "final_decision")
TASK_TO_AGENT = {
    "self_reflection": "self_reflection_manager",
    "final_decision": "portfolio_manager",
}
AGENT_LLM_LEVELS = {
    "portfolio_manager": "deep_llm",
    "self_reflection_manager": "quick_llm",
}


def test_portfolio_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert tuple(tasks) == TASK_KEYS


def test_portfolio_agents_keep_runtime_settings():
    agents = _load_yaml("agents.yaml")

    for agent_name, agent_config in agents.items():
        assert agent_config["llm_level"] == AGENT_LLM_LEVELS[agent_name]
        assert "llm" not in agent_config
        assert agent_config["allow_delegation"] is False
        assert agent_config["verbose"] is True

    # The deep model is used only for the final decision.
    assert agents["portfolio_manager"]["llm_level"] == "deep_llm"
    assert agents["self_reflection_manager"]["llm_level"] == "quick_llm"
    assert "{lessons_line}" in agents["portfolio_manager"]["backstory"]


def test_portfolio_task_agent_references_match_agent_keys():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    for task_name, task_config in tasks.items():
        assert task_config["name"] == task_name
        assert task_config["agent"] == TASK_TO_AGENT[task_name]
        assert task_config["agent"] in agents

    assert "{benchmark_name}" in tasks["self_reflection"]["description"]
    assert "{raw_return}" in tasks["self_reflection"]["description"]
    assert "{alpha_return}" in tasks["self_reflection"]["description"]
    assert "{final_decision}" in tasks["self_reflection"]["description"]
    for placeholder in ("{ticker}", "{investment_plan}", "{trader_plan}", "{history}"):
        assert placeholder in tasks["final_decision"]["description"]


def test_portfolio_tasks_bind_expected_agents():
    crew_source = PortfolioCrew()

    for task_name, agent_name in TASK_TO_AGENT.items():
        task = getattr(crew_source, task_name)()
        agent = getattr(crew_source, agent_name)()
        assert task.name == task_name
        assert task.agent is not None
        assert task.agent.role == agent.role


def test_final_decision_uses_portfolio_decision_output():
    from trading_agents.schemas import PortfolioDecision

    task = PortfolioCrew().final_decision()
    assert task.output_pydantic is PortfolioDecision


def test_portfolio_agents_resolve_configured_llm_levels(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "quick-model")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "deep-model")
    get_settings.cache_clear()
    crew_source = PortfolioCrew()

    assert crew_source.portfolio_manager().llm.model == "deep-model"
    assert crew_source.self_reflection_manager().llm.model == "quick-model"
    get_settings.cache_clear()


def test_portfolio_crew_enables_tracing_and_runs_tasks_sequentially():
    crew = PortfolioCrew().crew()

    assert crew.tracing is True
    assert crew.process == Process.sequential
    assert [task.name for task in crew.tasks] == list(TASK_KEYS)


def _load_yaml(file_name: str):
    return yaml.safe_load(_read_config(file_name))


def _read_config(file_name: str) -> str:
    config_path = portfolio_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    with open(config_path, encoding="utf-8") as file:
        return file.read()
