"""Tests for the DuckDB-backed evaluation dataset and dataset-backed tools."""

from __future__ import annotations

import pytest

from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation.eval_tools import build_dataset_tools


@pytest.fixture()
def dataset(tmp_path):
    db = EvalDataset(tmp_path / "eval.duckdb")
    yield db
    db.close()


def test_tool_output_round_trip(dataset):
    dataset.put_tool_output("get_stock_data", "aapl", "2024-01-03", "CSV BLOCK")
    # Ticker lookups are case-insensitive.
    assert dataset.tool_output("get_stock_data", "AAPL", "2024-01-03") == "CSV BLOCK"


def test_tool_output_upsert_replaces(dataset):
    dataset.put_tool_output("get_news", "AAPL", "2024-01-03", "v1")
    dataset.put_tool_output("get_news", "AAPL", "2024-01-03", "v2")
    assert dataset.tool_output("get_news", "AAPL", "2024-01-03") == "v2"


def test_missing_tool_output_raises(dataset):
    with pytest.raises(KeyError):
        dataset.tool_output("get_news", "AAPL", "2024-01-03")


def test_close_series_sorted_ascending(dataset):
    dataset.put_prices("SPY", [("2024-01-03", 470.0), ("2024-01-02", 469.0)])
    assert dataset.close_series("SPY") == [
        ("2024-01-02", 469.0),
        ("2024-01-03", 470.0),
    ]


def test_transaction_days_filters_to_window(dataset):
    dataset.put_prices(
        "SPY",
        [
            ("2023-12-29", 1.0),  # before window
            ("2024-01-02", 2.0),
            ("2024-01-03", 3.0),
            ("2024-04-05", 4.0),  # after window
        ],
    )
    days = dataset.transaction_days(
        benchmark="SPY", start_date="2024-01-01", end_date="2024-03-29"
    )
    assert days == ["2024-01-02", "2024-01-03"]


def test_dataset_backed_tool_returns_recorded_payload(dataset):
    dataset.put_tool_output("get_indicators", "AAPL", "2024-01-03", "INDICATORS")
    tools = build_dataset_tools(dataset, "AAPL", "2024-01-03")
    # _run ignores whatever arguments the model would pass.
    assert tools["get_indicators"]._run(ticker="AAPL", start_date="x", end_date="y") == (
        "INDICATORS"
    )
    assert tools["get_stock_data"].name == "get_stock_data"


def test_read_only_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        EvalDataset(tmp_path / "does_not_exist.duckdb", read_only=True)
