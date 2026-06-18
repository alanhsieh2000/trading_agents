"""Tests for the evaluation dataset builder entrypoint."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation import build_dataset
from trading_agents.evaluation.reddit_coverage import RedditPost


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
    assert options.lookback_days == 7
    assert options.news_limit == 40
    assert options.global_news_limit == 20
    assert options.global_news_lookback_days == 7
    assert options.verify_only is True


def test_options_use_plan_b_defaults_when_requested():
    args = build_dataset.parse_args(["--verify-only"])
    options = build_dataset.options_from_settings(args, plan_b_defaults=True)

    assert options.dataset_path == "data/eval_dataset_2026q1.duckdb"
    assert options.start_date == "2026-01-01"
    assert options.end_date == "2026-03-31"
    assert options.buffer_start_date == "2025-12-01"
    assert options.reddit_limit_per_sub == 5
    assert options.reddit_request_delay_seconds == 10.0


def test_reddit_cli_overrides_are_configurable():
    args = build_dataset.parse_args(
        ["--verify-only", "--reddit-delay", "0", "--reddit-limit-per-sub", "2"]
    )
    options = build_dataset.options_from_settings(args, plan_b_defaults=True)

    assert options.reddit_request_delay_seconds == 0.0
    assert options.reddit_limit_per_sub == 2


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
        lookback_days=7,
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


def test_build_stock_data_outputs_writes_tickers_and_benchmark(monkeypatch, tmp_path):
    calls = []

    def fake_get_stock_data_text(ticker, start_date, end_date):
        calls.append((ticker, start_date, end_date))
        return f"{ticker} {start_date} {end_date}"

    monkeypatch.setattr(
        build_dataset, "get_stock_data_text", fake_get_stock_data_text
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_stock_data_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_payload = dataset.tool_output("get_stock_data", "AAPL", "2025-12-02")
        spy_payload = dataset.tool_output("get_stock_data", "SPY", "2025-12-03")

    assert calls == [
        ("AAPL", "2025-11-29", "2025-12-02"),
        ("AAPL", "2025-11-30", "2025-12-03"),
        ("SPY", "2025-11-29", "2025-12-02"),
        ("SPY", "2025-11-30", "2025-12-03"),
    ]
    assert result.tool_name == "get_stock_data"
    assert result.symbols == ("AAPL", "SPY")
    assert result.payloads_written == 4
    assert result.lookback_days == 3
    assert aapl_payload == "AAPL 2025-11-29 2025-12-02"
    assert spy_payload == "SPY 2025-11-30 2025-12-03"


def test_indicator_names_for_dataset_collects_all_allowed_indicators():
    assert build_dataset.indicator_names_for_dataset() == tuple(
        sorted(build_dataset.ALLOWED_INDICATORS)
    )


def test_build_indicator_outputs_writes_tickers_only_with_all_indicators(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_indicators_text(ticker, start_date, end_date, indicators):
        calls.append((ticker, start_date, end_date, tuple(indicators)))
        return f"{ticker} {start_date} {end_date} {len(indicators)}"

    monkeypatch.setattr(
        build_dataset, "get_indicators_text", fake_get_indicators_text
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_indicator_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_payload = dataset.tool_output("get_indicators", "AAPL", "2025-12-02")
        googl_payload = dataset.tool_output("get_indicators", "GOOGL", "2025-12-03")

    all_indicators = build_dataset.indicator_names_for_dataset()
    assert calls == [
        ("AAPL", "2025-11-29", "2025-12-02", all_indicators),
        ("AAPL", "2025-11-30", "2025-12-03", all_indicators),
        ("GOOGL", "2025-11-29", "2025-12-02", all_indicators),
        ("GOOGL", "2025-11-30", "2025-12-03", all_indicators),
    ]
    assert result.tool_name == "get_indicators"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 3
    assert aapl_payload == f"AAPL 2025-11-29 2025-12-02 {len(all_indicators)}"
    assert googl_payload == f"GOOGL 2025-11-30 2025-12-03 {len(all_indicators)}"


def test_build_news_outputs_writes_tickers_only_with_doubled_limit(monkeypatch, tmp_path):
    calls = []

    def fake_fetch_news_via_exa(query, start_date, end_date, limit):
        calls.append((query, start_date, end_date, limit))
        return f"{query} news {start_date} {end_date} {limit}"

    monkeypatch.setattr(build_dataset, "fetch_news_via_exa", fake_fetch_news_via_exa)
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        news_limit=12,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_news_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_payload = dataset.tool_output("get_news", "AAPL", "2025-12-02")
        googl_payload = dataset.tool_output("get_news", "GOOGL", "2025-12-03")

    assert calls == [
        ("AAPL", "2025-11-29", "2025-12-02", 12),
        ("AAPL", "2025-11-30", "2025-12-03", 12),
        ("GOOGL", "2025-11-29", "2025-12-02", 12),
        ("GOOGL", "2025-11-30", "2025-12-03", 12),
    ]
    assert result.tool_name == "get_news"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 3
    assert aapl_payload == "AAPL news 2025-11-29 2025-12-02 12"
    assert googl_payload == "GOOGL news 2025-11-30 2025-12-03 12"


def test_build_news_outputs_records_fetch_errors(monkeypatch, tmp_path):
    def fake_fetch_news_via_exa(query, start_date, end_date, limit):
        raise TimeoutError("source timed out")

    monkeypatch.setattr(build_dataset, "fetch_news_via_exa", fake_fetch_news_via_exa)
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-02",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        news_limit=12,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_news_outputs(options, dataset, ["2025-12-02"])
        payload = dataset.tool_output("get_news", "AAPL", "2025-12-02")

    assert result.payloads_written == 1
    assert payload == "Error fetching news for AAPL: source timed out"


def test_build_global_news_outputs_writes_ticker_rows_with_doubled_limit(
    monkeypatch, tmp_path
):
    calls = []

    def fake_fetch_global_news_via_exa(curr_date, look_back_days, limit):
        calls.append((curr_date, look_back_days, limit))
        return f"global news {curr_date} {look_back_days} {limit}"

    monkeypatch.setattr(
        build_dataset, "fetch_global_news_via_exa", fake_fetch_global_news_via_exa
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        global_news_limit=14,
        global_news_lookback_days=5,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_global_news_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_payload = dataset.tool_output("get_global_news", "AAPL", "2025-12-02")
        googl_payload = dataset.tool_output("get_global_news", "GOOGL", "2025-12-03")

    assert calls == [
        ("2025-12-02", 5, 14),
        ("2025-12-03", 5, 14),
    ]
    assert result.tool_name == "get_global_news"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 5
    assert aapl_payload == "global news 2025-12-02 5 14"
    assert googl_payload == "global news 2025-12-03 5 14"


def test_build_global_news_outputs_records_fetch_errors(monkeypatch, tmp_path):
    def fake_fetch_global_news_via_exa(curr_date, look_back_days, limit):
        raise TimeoutError("global source timed out")

    monkeypatch.setattr(
        build_dataset, "fetch_global_news_via_exa", fake_fetch_global_news_via_exa
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-02",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        global_news_limit=14,
        global_news_lookback_days=5,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_global_news_outputs(options, dataset, ["2025-12-02"])
        aapl_payload = dataset.tool_output("get_global_news", "AAPL", "2025-12-02")
        googl_payload = dataset.tool_output("get_global_news", "GOOGL", "2025-12-02")

    assert result.payloads_written == 2
    assert aapl_payload == "Error fetching global news for 2025-12-02: global source timed out"
    assert googl_payload == aapl_payload


def _reddit_post(
    ticker: str,
    subreddit: str,
    yyyy_mm_dd: str,
    title: str | None = None,
) -> RedditPost:
    published_at = datetime.fromisoformat(yyyy_mm_dd + "T12:00:00+00:00")
    return RedditPost(
        ticker=ticker,
        subreddit=subreddit,
        title=title or f"{ticker} {subreddit} {yyyy_mm_dd}",
        published_at=published_at,
        published_date=published_at.date(),
        url=f"https://reddit.example/comments/{ticker}-{subreddit}-{yyyy_mm_dd}/x",
        body=f"{ticker} body {yyyy_mm_dd}",
    )


def test_fetch_reddit_posts_for_dataset_or_joins_aliases_and_keeps_all(monkeypatch):
    calls = []
    sleeps = []

    def fake_fetch_rss_posts(*, ticker, subreddit, query):
        calls.append((ticker, subreddit, query))
        return [_reddit_post(ticker, subreddit, "2026-01-02")]

    monkeypatch.setattr(build_dataset, "fetch_rss_posts", fake_fetch_rss_posts)
    monkeypatch.setattr(build_dataset.time, "sleep", sleeps.append)

    posts = build_dataset.fetch_reddit_posts_for_dataset(
        tickers=("AAPL", "GOOGL"),
        subreddits=("stocks", "investing"),
        request_delay_seconds=10.0,
    )

    assert len(posts) == 4
    assert calls == [
        ("AAPL", "stocks", "AAPL OR $AAPL OR Apple"),
        ("AAPL", "investing", "AAPL OR $AAPL OR Apple"),
        ("GOOGL", "stocks", "GOOGL OR $GOOGL OR Google"),
        ("GOOGL", "investing", "GOOGL OR $GOOGL OR Google"),
    ]
    assert sleeps == [10.0, 10.0, 10.0]


def test_build_reddit_outputs_stores_all_posts_but_limits_replay_payload(
    monkeypatch, tmp_path
):
    posts = [
        _reddit_post("AAPL", "stocks", "2026-01-01", "old"),
        _reddit_post("AAPL", "stocks", "2026-01-02", "new"),
        _reddit_post("AAPL", "investing", "2026-01-02", "investing"),
        _reddit_post("GOOGL", "stocks", "2026-01-02", "googl"),
    ]

    monkeypatch.setattr(
        build_dataset,
        "fetch_reddit_posts_for_dataset",
        lambda **_kwargs: posts,
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2026-01-02",
        end_date="2026-01-02",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        reddit_limit_per_sub=1,
        reddit_request_delay_seconds=10.0,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_reddit_outputs(options, dataset, ["2026-01-02"])
        raw_rows = dataset.reddit_post_rows()
        aapl_payload = dataset.tool_output("fetch_reddit_posts", "AAPL", "2026-01-02")
        googl_payload = dataset.tool_output("fetch_reddit_posts", "GOOGL", "2026-01-02")

    assert result.tool_name == "fetch_reddit_posts"
    assert result.posts_written == 4
    assert result.payloads_written == 2
    assert len(raw_rows) == 4
    assert "new" in aapl_payload
    assert "old" not in aapl_payload
    assert "investing" in aapl_payload
    assert "googl" in googl_payload


def test_build_fundamentals_outputs_writes_tickers_only_and_reuses_snapshot(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_fundamentals_text(ticker):
        calls.append(ticker)
        return f"{ticker} fundamentals snapshot"

    monkeypatch.setattr(
        build_dataset, "get_fundamentals_text", fake_get_fundamentals_text
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL", "AAPL", "GOOGL"),
        benchmark="SPY",
        start_date="2025-12-02",
        end_date="2025-12-04",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=3,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_fundamentals_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_first = dataset.tool_output("get_fundamentals", "AAPL", "2025-12-02")
        aapl_second = dataset.tool_output("get_fundamentals", "AAPL", "2025-12-03")
        googl_payload = dataset.tool_output("get_fundamentals", "GOOGL", "2025-12-03")

    assert calls == ["AAPL", "GOOGL"]
    assert result.tool_name == "get_fundamentals"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 0
    assert aapl_first == "AAPL fundamentals snapshot"
    assert aapl_second == aapl_first
    assert googl_payload == "GOOGL fundamentals snapshot"


def test_plan_b_main_builds_plan_b_dataset_path(monkeypatch, tmp_path, capsys):
    dataset_path = tmp_path / "eval_dataset_2026q1.duckdb"
    monkeypatch.setattr(build_dataset, "PLAN_B_DATASET_PATH", str(dataset_path))
    monkeypatch.setattr(
        build_dataset.yf,
        "download",
        lambda *args, **kwargs: _price_history("2026-01-02", 4),
    )
    monkeypatch.setattr(
        build_dataset,
        "get_stock_data_text",
        lambda ticker, start_date, end_date: f"{ticker} {start_date} {end_date}",
    )
    monkeypatch.setattr(
        build_dataset,
        "get_indicators_text",
        lambda ticker, start_date, end_date, indicators: (
            f"{ticker} {start_date} {end_date} {len(indicators)}"
        ),
    )
    monkeypatch.setattr(
        build_dataset,
        "fetch_news_via_exa",
        lambda ticker, start_date, end_date, limit: (
            f"{ticker} news {start_date} {end_date} {limit}"
        ),
    )
    monkeypatch.setattr(
        build_dataset,
        "fetch_global_news_via_exa",
        lambda curr_date, look_back_days, limit: (
            f"global news {curr_date} {look_back_days} {limit}"
        ),
    )
    monkeypatch.setattr(build_dataset, "fetch_reddit_posts_for_dataset", lambda **_: [])
    monkeypatch.setattr(
        build_dataset,
        "get_fundamentals_text",
        lambda ticker: f"{ticker} fundamentals snapshot",
    )

    exit_code = build_dataset.plan_b_main(["--tickers", "AAPL", "--limit-days", "2"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert dataset_path.exists()
    assert f"dataset_path: {dataset_path}" in output
    assert "window: 2026-01-01..2026-03-31" in output
    assert "Price table built" in output
    assert "get_stock_data outputs built" in output
    assert "get_indicators outputs built" in output
    assert "get_news outputs built" in output
    assert "get_global_news outputs built" in output
    assert "fetch_reddit_posts outputs built" in output
    assert "get_fundamentals outputs built" in output
    assert "payloads_written: 4" in output
    assert "payloads_written: 2" in output
    assert "remaining tool-output builders: pending" in output
    with EvalDataset(dataset_path, read_only=True) as dataset:
        assert dataset.close_series("AAPL")
        assert dataset.close_series("SPY")
        assert dataset.tool_output("get_stock_data", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_stock_data", "SPY", "2026-01-03")
        assert dataset.tool_output("get_indicators", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_news", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_global_news", "AAPL", "2026-01-02")
        assert dataset.tool_output("fetch_reddit_posts", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_fundamentals", "AAPL", "2026-01-02")
