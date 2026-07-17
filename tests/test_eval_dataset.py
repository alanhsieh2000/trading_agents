"""Tests for the DuckDB-backed evaluation dataset and dataset-backed tools."""

from __future__ import annotations

import duckdb
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


def test_tool_outputs_batch_upserts_all_rows(dataset):
    dataset.put_tool_outputs(
        [
            ("fetch_reddit_posts", "aapl", "2024-01-02", "AAPL payload"),
            ("fetch_reddit_posts", "googl", "2024-01-02", "GOOGL payload"),
        ]
    )

    assert (
        dataset.tool_output("fetch_reddit_posts", "AAPL", "2024-01-02")
        == "AAPL payload"
    )
    assert (
        dataset.tool_output("fetch_reddit_posts", "GOOGL", "2024-01-02")
        == "GOOGL payload"
    )


def test_tool_outputs_batch_rolls_back_every_row_on_failure(dataset):
    dataset.put_tool_output("fetch_reddit_posts", "AAPL", "2024-01-02", "old")

    with pytest.raises(duckdb.ConstraintException):
        dataset.put_tool_outputs(
            [
                ("fetch_reddit_posts", "AAPL", "2024-01-02", "new"),
                # A null payload violates the table contract after the first upsert.
                ("fetch_reddit_posts", "GOOGL", "2024-01-02", None),  # type: ignore[list-item]
            ]
        )

    assert dataset.tool_output("fetch_reddit_posts", "AAPL", "2024-01-02") == "old"
    with pytest.raises(KeyError):
        dataset.tool_output("fetch_reddit_posts", "GOOGL", "2024-01-02")


def test_replace_matching_tool_outputs_is_guarded_and_atomic(dataset):
    dataset.put_tool_output("get_news", "AAPL", "2024-01-02", "old")
    dataset.put_tool_output("get_news", "AAPL", "2024-01-03", "changed")

    with pytest.raises(RuntimeError, match="no rows were updated"):
        dataset.replace_matching_tool_outputs(
            "get_news",
            "AAPL",
            {"2024-01-02": "new 1", "2024-01-03": "new 2"},
            expected_payload="old",
        )

    assert dataset.tool_output("get_news", "AAPL", "2024-01-02") == "old"
    assert dataset.tool_output("get_news", "AAPL", "2024-01-03") == "changed"


def test_missing_tool_output_raises(dataset):
    with pytest.raises(KeyError):
        dataset.tool_output("get_news", "AAPL", "2024-01-03")


def test_close_series_sorted_ascending(dataset):
    dataset.put_prices("SPY", [("2024-01-03", 470.0), ("2024-01-02", 469.0)])
    assert dataset.close_series("SPY") == [
        ("2024-01-02", 469.0),
        ("2024-01-03", 470.0),
    ]


def test_reddit_post_rows_round_trip_keeps_ticker_specific_matches(dataset):
    rows = [
        (
            "aapl",
            "stocks",
            "2026-01-02T12:00:00+00:00",
            "2026-01-02",
            "https://reddit.example/comments/abc/shared",
            "AAPL title",
            "AAPL body",
            "abc",
            12,
            8,
        ),
        (
            "googl",
            "stocks",
            "2026-01-02T12:00:00+00:00",
            "2026-01-02",
            "https://reddit.example/comments/abc/shared",
            "GOOGL title",
            "GOOGL body",
            "abc",
            7,
            4,
        ),
    ]

    dataset.put_reddit_posts(rows)
    updated = rows[0][:6] + ("AAPL body v2",) + rows[0][7:]
    dataset.put_reddit_posts([updated])

    all_rows = dataset.reddit_post_rows()
    assert len(all_rows) == 2
    assert dataset.reddit_post_rows("AAPL") == [
        {
            "ticker": "AAPL",
            "subreddit": "stocks",
            "published_at": "2026-01-02T12:00:00+00:00",
            "published_date": "2026-01-02",
            "url": "https://reddit.example/comments/abc/shared",
            "title": "AAPL title",
            "body": "AAPL body v2",
            "source_post_id": "abc",
            "score": "12",
            "num_comments": "8",
        }
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
