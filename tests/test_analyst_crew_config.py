from crewai import Process
from crewai.crews.crew_output import CrewOutput
from crewai.tasks.task_output import TaskOutput
import yaml

from trading_agents.crews.analyst_crew import analyst_crew as analyst_module
from trading_agents.crews.analyst_crew.analyst_crew import (
    AnalystCrew,
    extract_analyst_reports,
    run_analyst_stage,
)


AGENT_KEYS = {"analyst"}
TASK_KEYS = (
    "market_analysis",
    "sentiment_analysis",
    "news_analysis",
    "fundamentals_analysis",
)
EXPECTED_TASK_TOOL_NAMES = {
    "market_analysis": ["get_stock_data", "get_indicators"],
    "sentiment_analysis": [],
    "news_analysis": ["get_news", "get_global_news"],
    "fundamentals_analysis": [
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    ],
}


def test_analyst_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert tuple(tasks) == TASK_KEYS


def test_single_analyst_agent_keeps_runtime_settings():
    agent_config = _load_yaml("agents.yaml")["analyst"]

    assert agent_config["llm"] == "gpt-4o-mini"
    assert agent_config["allow_delegation"] is False
    assert agent_config["verbose"] is True
    assert "{ticker}" in agent_config["goal"]
    assert "{current_date}" in agent_config["backstory"]


def test_task_agent_references_match_single_agent():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    for task_key, task_config in tasks.items():
        assert task_config["name"] == task_key
        assert task_config["agent"] == "analyst"
        assert task_config["agent"] in agents
        assert task_config["markdown"] is True


def test_analyst_yaml_uses_current_date_not_trade_date():
    agents_yaml = _read_config("agents.yaml")
    tasks_yaml = _read_config("tasks.yaml")

    assert "{current_date}" in agents_yaml
    assert "{trade_date}" not in agents_yaml
    assert "{trade_date}" not in tasks_yaml


def test_analyst_agent_has_no_tools():
    agent = AnalystCrew().analyst()

    assert agent.tools == []


def test_analyst_tasks_bind_same_agent_and_task_tools():
    crew_source = AnalystCrew()

    for task_key in TASK_KEYS:
        task = getattr(crew_source, task_key)()
        assert task.name == task_key
        assert task.agent is not None
        assert (
            task.agent.role.strip()
            == "a helpful AI assistant, collaborating with other assistants."
        )
        assert [tool.name for tool in task.tools] == EXPECTED_TASK_TOOL_NAMES[task_key]


def test_analyst_crew_enables_tracing_and_runs_tasks_sequentially():
    crew = AnalystCrew().crew()

    assert crew.tracing is True
    assert crew.process == Process.sequential
    assert len(crew.agents) == 1
    assert [agent.role.strip() for agent in crew.agents] == [
        "a helpful AI assistant, collaborating with other assistants."
    ]
    assert [task.name for task in crew.tasks] == list(TASK_KEYS)


def test_extract_analyst_reports_returns_all_reports_by_name():
    output = _crew_output(
        [
            ("market_analysis", "market text"),
            ("sentiment_analysis", "sentiment text"),
            ("news_analysis", "news text"),
            ("fundamentals_analysis", "fundamentals text"),
        ]
    )

    assert extract_analyst_reports(output) == {
        "market_report": "market text",
        "sentiment_report": "sentiment text",
        "news_report": "news text",
        "fundamentals_report": "fundamentals text",
    }


def test_prepare_analyst_inputs_reuses_supplied_sentiment_blocks(monkeypatch):
    class FailingNewsTool:
        def _run(self, *args, **kwargs):
            raise AssertionError("news prefetch should not run when block is supplied")

    def fail_prefetch(*args, **kwargs):
        raise AssertionError("sentiment prefetch should not run when block is supplied")

    monkeypatch.setattr(analyst_module, "get_news", FailingNewsTool())
    monkeypatch.setattr(analyst_module, "fetch_stocktwits_messages", fail_prefetch)
    monkeypatch.setattr(analyst_module, "fetch_reddit_posts", fail_prefetch)

    prepared = analyst_module.prepare_analyst_inputs(
        {
            "ticker": "nvda",
            "trade_date": "2024-05-24",
            "current_date": "2024-05-25",
            "start_date": "2020-01-01",
            "end_date": "2020-01-02",
            "sentiment_start_date": "2020-01-03",
            "news_sentiment_block": "news fixture",
            "stocktwits_block": "stocktwits fixture",
            "reddit_block": "reddit fixture",
        }
    )

    assert prepared["ticker"] == "NVDA"
    assert prepared["trade_date"] == "2024-05-25"
    assert prepared["current_date"] == "2024-05-25"
    assert prepared["start_date"] == "2024-05-18"
    assert prepared["end_date"] == "2024-05-25"
    assert prepared["sentiment_start_date"] == "2024-05-18"
    assert prepared["asset_label"] == "NVDA"
    assert prepared["news_sentiment_block"] == "news fixture"
    assert prepared["news_block"] == "news fixture"


def test_prepare_analyst_inputs_prefetches_with_current_date_window(monkeypatch):
    captured_news_args = {}

    class CapturingNewsTool:
        def _run(self, *args, **kwargs):
            captured_news_args["args"] = args
            captured_news_args["kwargs"] = kwargs
            return "prefetched news"

    monkeypatch.setattr(analyst_module, "get_news", CapturingNewsTool())
    monkeypatch.setattr(
        analyst_module,
        "fetch_stocktwits_messages",
        lambda ticker, limit=30: "stocktwits",
    )
    monkeypatch.setattr(analyst_module, "fetch_reddit_posts", lambda ticker: "reddit")

    prepared = analyst_module.prepare_analyst_inputs(
        {
            "ticker": "msft",
            "current_date": "2024-06-10",
        }
    )

    assert captured_news_args["args"] == ("MSFT", "2024-06-03", "2024-06-10")
    assert captured_news_args["kwargs"] == {"limit": 10}
    assert prepared["trade_date"] == "2024-06-10"
    assert prepared["current_date"] == "2024-06-10"
    assert prepared["start_date"] == "2024-06-03"
    assert prepared["end_date"] == "2024-06-10"
    assert prepared["sentiment_start_date"] == "2024-06-03"
    assert prepared["news_block"] == "prefetched news"
    assert prepared["stocktwits_block"] == "stocktwits"
    assert prepared["reddit_block"] == "reddit"


def test_run_analyst_stage_uses_mocked_sequential_crew(monkeypatch):
    captured_inputs = {}

    class FakeCrew:
        def kickoff(self, inputs):
            captured_inputs.update(inputs)
            return _crew_output(
                [
                    ("market_analysis", "market report"),
                    ("sentiment_analysis", "sentiment report"),
                    ("news_analysis", "news report"),
                    ("fundamentals_analysis", "fundamentals report"),
                ]
            )

    class FakeAnalystCrew:
        def crew(self):
            return FakeCrew()

    monkeypatch.setattr(analyst_module, "AnalystCrew", FakeAnalystCrew)

    result = run_analyst_stage(
        {
            "ticker": "nvda",
            "trade_date": "2024-05-24",
            "news_sentiment_block": "news fixture",
            "stocktwits_block": "stocktwits fixture",
            "reddit_block": "reddit fixture",
        }
    )

    assert captured_inputs["ticker"] == "NVDA"
    assert captured_inputs["current_date"] == "2024-05-24"
    assert captured_inputs["start_date"] == "2024-05-17"
    assert captured_inputs["end_date"] == "2024-05-24"
    assert captured_inputs["sentiment_start_date"] == "2024-05-17"
    assert result == {
        "market_report": "market report",
        "sentiment_report": "sentiment report",
        "news_report": "news report",
        "fundamentals_report": "fundamentals report",
    }


def _load_yaml(file_name: str):
    return yaml.safe_load(_read_config(file_name))


def _read_config(file_name: str) -> str:
    config_path = analyst_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    with open(config_path, encoding="utf-8") as file:
        return file.read()


def _crew_output(rows: list[tuple[str, str]]) -> CrewOutput:
    task_outputs = [
        TaskOutput(
            name=name,
            description=f"{name} description",
            expected_output=f"{name} expected output",
            raw=raw,
            agent="test agent",
        )
        for name, raw in rows
    ]
    return CrewOutput(raw=task_outputs[-1].raw, tasks_output=task_outputs)
