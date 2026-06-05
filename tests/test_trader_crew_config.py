from crewai import Process
import yaml

from trading_agents.config import get_settings
from trading_agents.crews.trader_crew import trader_crew as trader_module
from trading_agents.crews.trader_crew.trader_crew import TraderCrew
from trading_agents.schemas import TraderProposal


AGENT_KEYS = {"trader_agent"}
TASK_KEYS = ("trader_decision",)


def test_trader_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert tuple(tasks) == TASK_KEYS


def test_trader_agent_keeps_runtime_settings():
    agents = _load_yaml("agents.yaml")
    agent_config = agents["trader_agent"]

    assert agent_config["llm_level"] == "quick_llm"
    assert "llm" not in agent_config
    assert agent_config["allow_delegation"] is False
    assert agent_config["verbose"] is True


def test_trader_task_agent_reference_matches_agent_key():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")
    task_config = tasks["trader_decision"]

    assert task_config["name"] == "trader_decision"
    assert task_config["agent"] == "trader_agent"
    assert task_config["agent"] in agents
    assert task_config["markdown"] is True


def test_trader_task_binds_expected_agent_and_structured_output():
    crew_source = TraderCrew()
    task = crew_source.trader_decision()

    assert task.name == "trader_decision"
    assert task.agent is not None
    assert task.agent.role == crew_source.trader_agent().role
    assert task.output_pydantic is TraderProposal


def test_trader_agent_resolves_configured_llm_level(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "gpt-4o-mini")
    get_settings.cache_clear()
    crew_source = TraderCrew()

    assert crew_source.trader_agent().llm.model == "gpt-4o-mini"
    get_settings.cache_clear()


def test_trader_crew_enables_tracing_and_runs_task_sequentially():
    crew = TraderCrew().crew()

    assert crew.tracing is True
    assert crew.process == Process.sequential
    assert [task.name for task in crew.tasks] == list(TASK_KEYS)


def _load_yaml(file_name: str):
    return yaml.safe_load(_read_config(file_name))


def _read_config(file_name: str) -> str:
    config_path = trader_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    with open(config_path, encoding="utf-8") as file:
        return file.read()
