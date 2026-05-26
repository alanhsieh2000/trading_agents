from crewai import Process
import yaml

from trading_agents.crews.research_crew import research_crew as research_module
from trading_agents.crews.research_crew.research_crew import ResearchCrew
from trading_agents.schemas import InvestmentPlan


AGENT_KEYS = {"bull_researcher", "bear_researcher", "research_manager"}
TASK_KEYS = ("bull_research", "bear_research", "research_management")
TASK_TO_AGENT = {
    "bull_research": "bull_researcher",
    "bear_research": "bear_researcher",
    "research_management": "research_manager",
}


def test_research_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert tuple(tasks) == TASK_KEYS


def test_research_agents_keep_runtime_settings():
    agents = _load_yaml("agents.yaml")

    for agent_key in AGENT_KEYS:
        agent_config = agents[agent_key]
        assert agent_config["llm"] == "gpt-4o-mini"
        assert agent_config["allow_delegation"] is False
        assert agent_config["verbose"] is True


def test_research_task_agent_references_match_agent_keys():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    for task_key, task_config in tasks.items():
        assert task_config["name"] == task_key
        assert task_config["agent"] == TASK_TO_AGENT[task_key]
        assert task_config["agent"] in agents
        assert task_config["markdown"] is True


def test_research_debate_prompts_require_has_more_trailer():
    tasks_yaml = _read_config("tasks.yaml")

    assert "HAS_MORE: yes" in tasks_yaml
    assert "HAS_MORE: no" in tasks_yaml


def test_research_tasks_bind_expected_agents_and_manager_output():
    crew_source = ResearchCrew()

    bull_task = crew_source.bull_research()
    bear_task = crew_source.bear_research()
    manager_task = crew_source.research_management()

    assert bull_task.name == "bull_research"
    assert bear_task.name == "bear_research"
    assert manager_task.name == "research_management"
    assert bull_task.agent is not None
    assert bear_task.agent is not None
    assert manager_task.agent is not None
    assert bull_task.agent.role == crew_source.bull_researcher().role
    assert bear_task.agent.role == crew_source.bear_researcher().role
    assert manager_task.agent.role == crew_source.research_manager().role
    assert manager_task.output_pydantic is InvestmentPlan


def test_research_crew_enables_tracing_and_runs_tasks_sequentially():
    crew = ResearchCrew().crew()

    assert crew.tracing is True
    assert crew.process == Process.sequential
    assert [task.name for task in crew.tasks] == list(TASK_KEYS)


def _load_yaml(file_name: str):
    return yaml.safe_load(_read_config(file_name))


def _read_config(file_name: str) -> str:
    config_path = research_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    with open(config_path, encoding="utf-8") as file:
        return file.read()
