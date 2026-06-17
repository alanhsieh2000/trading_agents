"""Tests for the evaluation dataset builder entrypoint."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation import build_dataset


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_options_use_plan_07_defaults():
    args = build_dataset.parse_args(["--verify-only"])

    options = build_dataset.options_from_settings(args)

    assert options.dataset_path == "data/eval_dataset.duckdb"
    assert options.tickers == ("AAPL", "GOOGL", "AMZN")
    assert options.benchmark == "SPY"
    assert options.start_date == "2024-01-01"
    assert options.end_date == "2024-03-29"
    assert options.buffer_start_date == "2023-12-01"
    assert options.verify_only is True


def test_options_use_plan_b_defaults_when_requested():
    args = build_dataset.parse_args(["--verify-only"])
    options = build_dataset.options_from_settings(args, plan_b_defaults=True)

    assert options.dataset_path == "data/eval_dataset_2026q1.duckdb"
    assert options.start_date == "2026-01-01"
    assert options.end_date == "2026-03-31"
    assert options.buffer_start_date == "2025-12-01"


def test_tickers_cli_override_settings():
    args = build_dataset.parse_args(["--verify-only", "--tickers", "aapl", "spy"])

    options = build_dataset.options_from_settings(args)

    assert options.tickers == ("AAPL", "SPY")


def test_verify_only_does_not_create_dataset(monkeypatch, tmp_path, capsys):
    dataset_path = tmp_path / "eval_dataset_2026q1.duckdb"
    monkeypatch.setattr(build_dataset, "PLAN_B_DATASET_PATH", str(dataset_path))

    exit_code = build_dataset.plan_b_main(["--verify-only"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert f"dataset_path: {dataset_path}" in output
    assert "window: 2026-01-01..2026-03-31" in output
    assert "verify-only: dataset writes skipped" in output
    assert not dataset_path.exists()


def _price_history(start: str, rows: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=rows, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + index for index in range(rows)],
            "High": [101 + index for index in range(rows)],
            "Low": [99 + index for index in range(rows)],
            "Close": [100.5 + index for index in range(rows)],
            "Adj Close": [100.5 + index for index in range(rows)],
            "Volume": [1000 + index for index in range(rows)],
        },
        index=dates,
    )


def test_build_price_table_writes_unique_symbols_and_limits_transaction_days(
    monkeypatch, tmp_path
):
    calls = []

    def fake_download(ticker, start, end, progress, auto_adjust):
        calls.append(
            {
                "ticker": ticker,
                "start": start,
                "end": end,
                "progress": progress,
                "auto_adjust": auto_adjust,
            }
        )
        return _price_history("2025-12-01", 6)

    monkeypatch.setattr(build_dataset.yf, "download", fake_download)
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "SPY"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=2,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_price_table(options, dataset)
        spy_rows = dataset.close_series("SPY")
        aapl_rows = dataset.close_series("AAPL")

    assert [call["ticker"] for call in calls] == ["AAPL", "SPY"]
    assert {call["start"] for call in calls} == {"2025-12-01"}
    assert {call["end"] for call in calls} == {"2025-12-07"}
    assert all(call["progress"] is False for call in calls)
    assert all(call["auto_adjust"] is False for call in calls)
    assert result.symbols == ("AAPL", "SPY")
    assert result.rows_by_symbol == {"AAPL": 6, "SPY": 6}
    assert result.transaction_days == ("2025-12-02", "2025-12-03")
    assert spy_rows[0] == ("2025-12-01", 100.5)
    assert aapl_rows[-1] == ("2025-12-06", 105.5)


def test_plan_b_main_builds_plan_b_dataset_path(monkeypatch, tmp_path, capsys):
    dataset_path = tmp_path / "eval_dataset_2026q1.duckdb"
    monkeypatch.setattr(build_dataset, "PLAN_B_DATASET_PATH", str(dataset_path))
    monkeypatch.setattr(
        build_dataset.yf,
        "download",
        lambda *args, **kwargs: _price_history("2026-01-02", 4),
    )

    exit_code = build_dataset.plan_b_main(["--tickers", "AAPL", "--limit-days", "2"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert dataset_path.exists()
    assert f"dataset_path: {dataset_path}" in output
    assert "window: 2026-01-01..2026-03-31" in output
    assert "Price table built" in output
    assert "tool-output builders: pending" in output
    with EvalDataset(dataset_path, read_only=True) as dataset:
        assert dataset.close_series("AAPL")
        assert dataset.close_series("SPY")
