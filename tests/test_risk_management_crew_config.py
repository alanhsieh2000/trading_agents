from crewai import Process
import yaml

from trading_agents.config import get_settings
from trading_agents.crews.risk_management_crew import risk_management_crew as risk_module
from trading_agents.crews.risk_management_crew.risk_management_crew import RiskManagementCrew


AGENT_KEYS = {
    "aggressive_analyst",
    "conservative_analyst",
    "neutral_analyst",
}
TASK_KEYS = (
    "aggressive_risk_analysis",
    "conservative_risk_analysis",
    "neutral_risk_analysis",
)
TASK_TO_AGENT = {
    "aggressive_risk_analysis": "aggressive_analyst",
    "conservative_risk_analysis": "conservative_analyst",
    "neutral_risk_analysis": "neutral_analyst",
}


def test_risk_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert tuple(tasks) == TASK_KEYS


def test_risk_agents_keep_runtime_settings():
    agents = _load_yaml("agents.yaml")

    for agent_config in agents.values():
        assert agent_config["llm_level"] == "quick_llm"
        assert "llm" not in agent_config
        assert agent_config["allow_delegation"] is False
        assert agent_config["verbose"] is True


def test_risk_task_agent_references_match_agent_keys():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    for task_name, task_config in tasks.items():
        assert task_config["name"] == task_name
        assert task_config["agent"] == TASK_TO_AGENT[task_name]
        assert task_config["agent"] in agents
        assert "HAS_MORE" not in task_config["expected_output"]
        assert "{history}" in task_config["description"]
        assert "{market_research_report}" in task_config["description"]


def test_risk_tasks_bind_expected_agents():
    crew_source = RiskManagementCrew()

    for task_name, agent_name in TASK_TO_AGENT.items():
        task = getattr(crew_source, task_name)()
        agent = getattr(crew_source, agent_name)()
        assert task.name == task_name
        assert task.agent is not None
        assert task.agent.role == agent.role


def test_risk_agent_resolves_configured_llm_level(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gpt-4o-mini")
    get_settings.cache_clear()
    crew_source = RiskManagementCrew()

    assert crew_source.aggressive_analyst().llm.model == "gpt-4o-mini"
    assert crew_source.conservative_analyst().llm.model == "gpt-4o-mini"
    assert crew_source.neutral_analyst().llm.model == "gpt-4o-mini"
    get_settings.cache_clear()


def test_risk_crew_enables_tracing_and_runs_tasks_sequentially():
    crew = RiskManagementCrew().crew()

    assert crew.tracing is True
    assert crew.process == Process.sequential
    assert [task.name for task in crew.tasks] == list(TASK_KEYS)


def _load_yaml(file_name: str):
    return yaml.safe_load(_read_config(file_name))


def _read_config(file_name: str) -> str:
    config_path = risk_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    with open(config_path, encoding="utf-8") as file:
        return file.read()
