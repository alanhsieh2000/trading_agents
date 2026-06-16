"""Tests for the evaluation dataset builder entrypoint."""

from __future__ import annotations

import pytest

from trading_agents.config import get_settings
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
