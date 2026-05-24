from crewai.crews.crew_output import CrewOutput
from crewai.tasks.task_output import TaskOutput
import yaml

from trading_agents.crews.analyst_crew import analyst_crew as analyst_module
from trading_agents.crews.analyst_crew.analyst_crew import (
    AnalystCrew,
    extract_analyst_reports,
    run_analyst_stage,
)


AGENT_KEYS = {
    "fundamentals_analyst",
    "sentiment_analyst",
    "news_analyst",
    "market_analyst",
}
TASK_KEYS = {
    "fundamentals_analysis",
    "sentiment_analysis",
    "news_analysis",
    "market_analysis",
}
EXPECTED_TOOL_NAMES = {
    "fundamentals_analyst": [
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    ],
    "sentiment_analyst": [],
    "news_analyst": ["get_news", "get_global_news"],
    "market_analyst": ["get_stock_data", "get_indicators"],
}


def test_analyst_yaml_keys_exist():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    assert set(agents) == AGENT_KEYS
    assert set(tasks) == TASK_KEYS


def test_analyst_agents_use_gpt_4o_mini():
    agents = _load_yaml("agents.yaml")

    for agent_config in agents.values():
        assert agent_config["llm"] == "gpt-4o-mini"


def test_task_agent_references_match_agents_yaml():
    agents = _load_yaml("agents.yaml")
    tasks = _load_yaml("tasks.yaml")

    for task_key, task_config in tasks.items():
        assert task_config["name"] == task_key
        assert task_config["agent"] in agents
        assert "{ticker}" in task_config["description"]
        assert "{trade_date}" in task_config["description"]


def test_analyst_crew_imports_and_wires_tools():
    crew = AnalystCrew()

    for agent_key, expected_tool_names in EXPECTED_TOOL_NAMES.items():
        agent = getattr(crew, agent_key)()
        assert [tool.name for tool in agent.tools] == expected_tool_names


def test_analyst_tasks_bind_agents_and_names():
    crew = AnalystCrew()

    for task_key in TASK_KEYS:
        task = getattr(crew, task_key)()
        assert task.name == task_key
        assert task.agent is not None


def test_analyst_crew_enables_tracing():
    crew = AnalystCrew().crew()

    assert crew.tracing is True


def test_extract_analyst_reports_returns_all_reports_by_name():
    output = _crew_output(
        [
            ("fundamentals_analysis", "fundamentals text"),
            ("sentiment_analysis", "sentiment text"),
            ("news_analysis", "news text"),
            ("market_analysis", "market text"),
        ]
    )

    assert extract_analyst_reports(output) == {
        "fundamentals_report": "fundamentals text",
        "sentiment_report": "sentiment text",
        "news_report": "news text",
        "market_report": "market text",
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
            "news_sentiment_block": "news fixture",
            "stocktwits_block": "stocktwits fixture",
            "reddit_block": "reddit fixture",
        }
    )

    assert prepared["ticker"] == "NVDA"
    assert prepared["sentiment_start_date"] == "2024-05-17"
    assert prepared["news_sentiment_block"] == "news fixture"


def test_run_analyst_stage_uses_mocked_parallel_tasks(monkeypatch):
    captured_inputs = {}

    def fake_run_parallel(inputs):
        captured_inputs.update(inputs)
        return _crew_output(
            [
                ("fundamentals_analysis", "fundamentals report"),
                ("sentiment_analysis", "sentiment report"),
                ("news_analysis", "news report"),
                ("market_analysis", "market report"),
            ]
        ).tasks_output

    monkeypatch.setattr(analyst_module, "run_parallel_analyst_tasks", fake_run_parallel)

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
    assert captured_inputs["sentiment_start_date"] == "2024-05-17"
    assert result == {
        "fundamentals_report": "fundamentals report",
        "sentiment_report": "sentiment report",
        "news_report": "news report",
        "market_report": "market report",
    }


def _load_yaml(file_name: str):
    config_path = (
        analyst_module.__file__.rsplit("/", 1)[0] + f"/config/{file_name}"
    )
    with open(config_path, encoding="utf-8") as file:
        return yaml.safe_load(file)


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
