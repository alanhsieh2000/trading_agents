"""Tests for the evaluation dataset builder entrypoint."""

from __future__ import annotations

from datetime import datetime
import json

import pandas as pd
import pytest

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.evaluation import build_dataset
from trading_agents.evaluation.reddit_coverage import RedditPost
from trading_agents.evaluation.build_dataset import StocktwitsMessage


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
    assert options.use_arctic_shift_reddit is True
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
    assert options.use_arctic_shift_reddit is False


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


def _write_arctic_page(tmp_path, ticker, subreddit, sequence, posts):
    raw_dir = tmp_path / "arctic-shift"
    raw_dir.mkdir(exist_ok=True)
    path = raw_dir / f"{ticker}-{subreddit}-{sequence}.json"
    path.write_text(json.dumps({"data": posts}))
    return raw_dir


def _arctic_post(post_id, yyyy_mm_dd, subreddit, *, score=10, comments=5):
    created_at = datetime.fromisoformat(yyyy_mm_dd + "T12:00:00+00:00")
    return {
        "id": post_id,
        "created_utc": int(created_at.timestamp()),
        "subreddit": subreddit,
        "title": f"title {post_id}",
        "selftext": f"body {post_id}",
        "score": score,
        "num_comments": comments,
    }


def _complete_arctic_archive(tmp_path, *, latest="2024-01-05"):
    raw_dir = None
    for subreddit in ("wallstreetbets", "stocks", "investing"):
        posts = [
            _arctic_post(f"{subreddit}-old", "2023-12-25", subreddit),
            _arctic_post(f"{subreddit}-new", latest, subreddit),
        ]
        raw_dir = _write_arctic_page(tmp_path, "AAPL", subreddit, 1, posts)
    return raw_dir


def test_load_arctic_shift_posts_validates_and_deduplicates(tmp_path):
    raw_dir = _complete_arctic_archive(tmp_path)
    path = raw_dir / "AAPL-stocks-1.json"
    payload = json.loads(path.read_text())
    payload["data"].append(dict(payload["data"][0]))
    path.write_text(json.dumps(payload))

    archive = build_dataset.load_arctic_shift_posts(raw_dir, ["AAPL"])

    assert archive.pages_by_symbol == {"AAPL": 3}
    assert archive.pages_by_stream[("AAPL", "stocks")] == 1
    assert len(archive.posts) == 6
    assert archive.posts[0].source_post_id == "investing-old"
    assert archive.posts[0].score == 10
    assert archive.posts[0].num_comments == 5


def test_load_arctic_shift_posts_rejects_missing_required_field(tmp_path):
    raw_dir = _complete_arctic_archive(tmp_path)
    path = raw_dir / "AAPL-stocks-1.json"
    payload = json.loads(path.read_text())
    del payload["data"][0]["score"]
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="missing required fields score"):
        build_dataset.load_arctic_shift_posts(raw_dir, ["AAPL"])


def test_validate_arctic_shift_coverage_rejects_short_archive(tmp_path):
    raw_dir = _complete_arctic_archive(tmp_path, latest="2024-01-03")
    archive = build_dataset.load_arctic_shift_posts(raw_dir, ["AAPL"])

    with pytest.raises(ValueError, match="Insufficient Arctic Shift archive coverage"):
        build_dataset.validate_arctic_shift_coverage(
            archive, ["AAPL"], ["2024-01-02", "2024-01-05"], lookback_days=7
        )


def test_build_reddit_outputs_uses_arctic_shift_without_network(monkeypatch, tmp_path):
    raw_dir = _complete_arctic_archive(tmp_path)
    stocks_path = raw_dir / "AAPL-stocks-1.json"
    stocks_page = json.loads(stocks_path.read_text())
    stocks_page["data"][-1]["score"] = 0
    stocks_page["data"][-1]["num_comments"] = 0
    stocks_path.write_text(json.dumps(stocks_page))
    monkeypatch.setattr(build_dataset, "ARCTIC_SHIFT_RAW_DIR", raw_dir)

    def unexpected_network(**_kwargs):
        raise AssertionError("live Reddit must not be called")

    monkeypatch.setattr(
        build_dataset, "fetch_reddit_posts_for_dataset", unexpected_network
    )
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2024-01-02",
        end_date="2024-01-05",
        buffer_start_date="2023-12-01",
        price_tail_days=2,
        lookback_days=7,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        reddit_limit_per_sub=1,
        use_arctic_shift_reddit=True,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_reddit_outputs(
            options, dataset, ["2024-01-02", "2024-01-05"]
        )
        payload = dataset.tool_output("fetch_reddit_posts", "AAPL", "2024-01-05")
        rows = dataset.reddit_post_rows("AAPL")

    assert result.source == "arctic-shift"
    assert result.pages_by_symbol == {"AAPL": 3}
    assert result.posts_written == 6
    assert "scores/comments unavailable" not in payload
    assert "[2024-01-05 ·   10↑ ·   5c] title" in payload
    assert "[2024-01-05 ·    0↑ ·   0c] title stocks-new" in payload
    assert rows[-1]["score"] == "10"
    assert rows[-1]["num_comments"] == "5"


def test_build_reddit_outputs_validates_before_writing(monkeypatch, tmp_path):
    raw_dir = _complete_arctic_archive(tmp_path, latest="2024-01-03")
    monkeypatch.setattr(build_dataset, "ARCTIC_SHIFT_RAW_DIR", raw_dir)
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2024-01-02",
        end_date="2024-01-05",
        buffer_start_date="2023-12-01",
        price_tail_days=2,
        lookback_days=7,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
        use_arctic_shift_reddit=True,
    )

    with EvalDataset(options.dataset_path) as dataset:
        dataset.put_tool_output("fetch_reddit_posts", "AAPL", "2024-01-02", "old")
        with pytest.raises(ValueError, match="Insufficient Arctic Shift"):
            build_dataset.build_reddit_outputs(
                options, dataset, ["2024-01-02", "2024-01-05"]
            )
        assert dataset.tool_output("fetch_reddit_posts", "AAPL", "2024-01-02") == "old"
        assert dataset.reddit_post_rows("AAPL") == []


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


def _stocktwits_payload(
    ticker: str,
    messages: list[dict],
    *,
    since: int = 3,
    max_id: int = 1,
) -> dict:
    return {
        "symbol": {"symbol": ticker},
        "cursor": {"more": True, "since": since, "max": max_id},
        "messages": messages,
    }


def _stocktwits_message(
    message_id: int,
    created_at: str,
    body: str,
    username: str = "user",
    sentiment: str | None = None,
) -> dict:
    entities = {"sentiment": {"basic": sentiment}} if sentiment else {}
    return {
        "id": message_id,
        "created_at": created_at,
        "body": body,
        "user": {"username": username},
        "entities": entities,
    }


def test_load_stocktwits_messages_dedupes_and_sorts_descending(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    first = _stocktwits_payload(
        "AAPL",
        [
            _stocktwits_message(2, "2026-01-03T12:00:00Z", "newer", "bull", "Bullish"),
            _stocktwits_message(1, "2026-01-02T12:00:00Z", "older"),
        ],
        since=3,
        max_id=2,
    )
    second = _stocktwits_payload(
        "AAPL",
        [
            _stocktwits_message(2, "2026-01-03T12:00:00Z", "newer", "bull", "Bullish"),
            _stocktwits_message(3, "2026-01-01T12:00:00Z", "oldest", "bear", "Bearish"),
        ],
        since=1,
        max_id=0,
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(first))
    (raw_dir / "AAPL-0002.json").write_text(json.dumps(second))

    messages = build_dataset.load_stocktwits_messages("aapl", raw_dir=raw_dir)

    assert [message.message_id for message in messages] == [2, 1, 3]
    assert messages[0].body == "newer"
    assert messages[0].sentiment == "Bullish"


def test_load_stocktwits_archive_rejects_missing_message_field(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    message = _stocktwits_message(2, "2024-01-03T12:00:00Z", "body")
    del message["body"]
    (raw_dir / "AAPL-0001.json").write_text(
        json.dumps(_stocktwits_payload("AAPL", [message]))
    )

    with pytest.raises(ValueError, match="missing required fields body"):
        build_dataset.load_stocktwits_archive(raw_dir, ["AAPL"])


def test_load_stocktwits_archive_rejects_noncontiguous_numeric_sequence(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    first = _stocktwits_payload(
        "AAPL",
        [_stocktwits_message(3, "2024-01-03T12:00:00Z", "new")],
        since=4,
        max_id=3,
    )
    third = _stocktwits_payload(
        "AAPL",
        [_stocktwits_message(1, "2024-01-01T12:00:00Z", "old")],
        since=2,
        max_id=1,
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(first))
    (raw_dir / "AAPL-0003.json").write_text(json.dumps(third))

    with pytest.raises(ValueError, match=r"missing pages: \[2\]"):
        build_dataset.load_stocktwits_archive(raw_dir, ["AAPL"])


def test_load_stocktwits_archive_rejects_conflicting_duplicate(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    first = _stocktwits_payload(
        "AAPL",
        [_stocktwits_message(2, "2024-01-03T12:00:00Z", "original")],
        since=3,
        max_id=2,
    )
    second = _stocktwits_payload(
        "AAPL",
        [_stocktwits_message(2, "2024-01-03T12:00:00Z", "changed")],
        since=1,
        max_id=0,
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(first))
    (raw_dir / "AAPL-0002.json").write_text(json.dumps(second))

    with pytest.raises(ValueError, match="Conflicting duplicate StockTwits message 2"):
        build_dataset.load_stocktwits_archive(raw_dir, ["AAPL"])


def test_validate_stocktwits_coverage_rejects_short_archive(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    payload = _stocktwits_payload(
        "AAPL",
        [
            _stocktwits_message(2, "2024-01-03T12:00:00Z", "new"),
            _stocktwits_message(1, "2024-01-01T12:00:00Z", "old"),
        ],
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(payload))
    archive = build_dataset.load_stocktwits_archive(raw_dir, ["AAPL"])

    with pytest.raises(ValueError, match="Insufficient StockTwits archive coverage"):
        build_dataset.validate_stocktwits_coverage(
            archive, ["AAPL"], ["2024-01-02", "2024-01-05"], lookback_days=7
        )


def test_render_stocktwits_payload_matches_live_helper_shape():
    messages = [
        StocktwitsMessage(
            ticker="AAPL",
            message_id=3,
            created_at=datetime.fromisoformat("2026-01-05T12:00:00+00:00"),
            body="bullish body",
            username="bull",
            sentiment="Bullish",
        ),
        StocktwitsMessage(
            ticker="AAPL",
            message_id=2,
            created_at=datetime.fromisoformat("2026-01-04T12:00:00+00:00"),
            body="bearish body",
            username="bear",
            sentiment="Bearish",
        ),
        StocktwitsMessage(
            ticker="AAPL",
            message_id=1,
            created_at=datetime.fromisoformat("2025-12-20T12:00:00+00:00"),
            body="too old",
            username="old",
            sentiment=None,
        ),
    ]

    payload = build_dataset.render_stocktwits_payload(
        "aapl", "2026-01-05", messages, lookback_days=7, limit=30
    )

    assert payload == (
        "Bullish: 1 (50%) · Bearish: 1 (50%) · Unlabeled: 0 · "
        "Total: 2 most-recent messages\n\n"
        "[2026-01-05T12:00:00Z · @bull · Bullish] bullish body\n"
        "[2026-01-04T12:00:00Z · @bear · Bearish] bearish body"
    )


def test_build_stocktwits_outputs_writes_lookback_payloads_from_raw_json(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    payload = _stocktwits_payload(
        "AAPL",
        [
            _stocktwits_message(3, "2026-01-03T12:00:00Z", "inside", "near", "Bullish"),
            _stocktwits_message(2, "2025-12-20T12:00:00Z", "outside", "far"),
        ],
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(payload))
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2026-01-02",
        end_date="2026-01-03",
        buffer_start_date="2025-12-01",
        price_tail_days=2,
        lookback_days=7,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        result = build_dataset.build_stocktwits_outputs(
            options, dataset, ["2026-01-02", "2026-01-03"], raw_dir=raw_dir
        )
        first_payload = dataset.tool_output(
            "fetch_stocktwits_messages", "AAPL", "2026-01-02"
        )
        second_payload = dataset.tool_output(
            "fetch_stocktwits_messages", "AAPL", "2026-01-03"
        )

    assert result.tool_name == "fetch_stocktwits_messages"
    assert result.payloads_written == 2
    assert first_payload == "No data available for StockTwits messages for AAPL."
    assert "inside" in second_payload
    assert "outside" not in second_payload


def test_build_stocktwits_outputs_validates_before_writing(tmp_path):
    raw_dir = tmp_path / "stocktwits"
    raw_dir.mkdir()
    payload = _stocktwits_payload(
        "AAPL",
        [_stocktwits_message(1, "2024-01-03T12:00:00Z", "too short")],
    )
    (raw_dir / "AAPL-0001.json").write_text(json.dumps(payload))
    options = build_dataset.BuildDatasetOptions(
        dataset_path=str(tmp_path / "eval.duckdb"),
        tickers=("AAPL",),
        benchmark="SPY",
        start_date="2024-01-02",
        end_date="2024-01-05",
        buffer_start_date="2023-12-01",
        price_tail_days=2,
        lookback_days=7,
        weight_over=0.5,
        weight_under=0.5,
        limit_days=None,
        verify_only=False,
    )

    with EvalDataset(options.dataset_path) as dataset:
        dataset.put_tool_output(
            "fetch_stocktwits_messages", "AAPL", "2024-01-02", "old"
        )
        with pytest.raises(ValueError, match="Insufficient StockTwits"):
            build_dataset.build_stocktwits_outputs(
                options,
                dataset,
                ["2024-01-02", "2024-01-05"],
                raw_dir=raw_dir,
            )
        assert (
            dataset.tool_output(
                "fetch_stocktwits_messages", "AAPL", "2024-01-02"
            )
            == "old"
        )


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


def test_build_balance_sheet_outputs_writes_tickers_only_and_reuses_snapshot(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_statement_text(ticker, statement_name, statement_attr):
        calls.append((ticker, statement_name, statement_attr))
        return f"{ticker} {statement_name} snapshot from {statement_attr}"

    monkeypatch.setattr(build_dataset, "get_statement_text", fake_get_statement_text)
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
        result = build_dataset.build_balance_sheet_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_first = dataset.tool_output("get_balance_sheet", "AAPL", "2025-12-02")
        aapl_second = dataset.tool_output("get_balance_sheet", "AAPL", "2025-12-03")
        googl_payload = dataset.tool_output("get_balance_sheet", "GOOGL", "2025-12-03")

    assert calls == [
        ("AAPL", "Balance sheet", "balance_sheet"),
        ("GOOGL", "Balance sheet", "balance_sheet"),
    ]
    assert result.tool_name == "get_balance_sheet"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 0
    assert aapl_first == "AAPL Balance sheet snapshot from balance_sheet"
    assert aapl_second == aapl_first
    assert googl_payload == "GOOGL Balance sheet snapshot from balance_sheet"


def test_build_cashflow_outputs_writes_tickers_only_and_reuses_snapshot(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_statement_text(ticker, statement_name, statement_attr):
        calls.append((ticker, statement_name, statement_attr))
        return f"{ticker} {statement_name} snapshot from {statement_attr}"

    monkeypatch.setattr(build_dataset, "get_statement_text", fake_get_statement_text)
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
        result = build_dataset.build_cashflow_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_first = dataset.tool_output("get_cashflow", "AAPL", "2025-12-02")
        aapl_second = dataset.tool_output("get_cashflow", "AAPL", "2025-12-03")
        googl_payload = dataset.tool_output("get_cashflow", "GOOGL", "2025-12-03")

    assert calls == [
        ("AAPL", "Cash flow statement", "cashflow"),
        ("GOOGL", "Cash flow statement", "cashflow"),
    ]
    assert result.tool_name == "get_cashflow"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 0
    assert aapl_first == "AAPL Cash flow statement snapshot from cashflow"
    assert aapl_second == aapl_first
    assert googl_payload == "GOOGL Cash flow statement snapshot from cashflow"


def test_build_income_statement_outputs_writes_tickers_only_and_reuses_snapshot(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_statement_text(ticker, statement_name, statement_attr):
        calls.append((ticker, statement_name, statement_attr))
        return f"{ticker} {statement_name} snapshot from {statement_attr}"

    monkeypatch.setattr(build_dataset, "get_statement_text", fake_get_statement_text)
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
        result = build_dataset.build_income_statement_outputs(
            options, dataset, ["2025-12-02", "2025-12-03"]
        )
        aapl_first = dataset.tool_output("get_income_statement", "AAPL", "2025-12-02")
        aapl_second = dataset.tool_output("get_income_statement", "AAPL", "2025-12-03")
        googl_payload = dataset.tool_output(
            "get_income_statement", "GOOGL", "2025-12-03"
        )

    assert calls == [
        ("AAPL", "Income statement", "income_stmt"),
        ("GOOGL", "Income statement", "income_stmt"),
    ]
    assert result.tool_name == "get_income_statement"
    assert result.symbols == ("AAPL", "GOOGL")
    assert result.payloads_written == 4
    assert result.lookback_days == 0
    assert aapl_first == "AAPL Income statement snapshot from income_stmt"
    assert aapl_second == aapl_first
    assert googl_payload == "GOOGL Income statement snapshot from income_stmt"


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
        "load_stocktwits_archive",
        lambda _raw_dir, tickers, **_: build_dataset.StockTwitsArchive(
            messages_by_symbol={ticker: () for ticker in tickers},
            pages_by_symbol={ticker: 1 for ticker in tickers},
            duplicates_by_symbol={ticker: 0 for ticker in tickers},
            date_range_by_symbol={
                ticker: (
                    datetime.fromisoformat("2025-12-01T00:00:00+00:00").date(),
                    datetime.fromisoformat("2026-03-31T00:00:00+00:00").date(),
                )
                for ticker in tickers
            },
        ),
    )
    monkeypatch.setattr(
        build_dataset,
        "get_fundamentals_text",
        lambda ticker: f"{ticker} fundamentals snapshot",
    )
    monkeypatch.setattr(
        build_dataset,
        "get_statement_text",
        lambda ticker, statement_name, statement_attr: (
            f"{ticker} {statement_name} snapshot from {statement_attr}"
        ),
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
    assert "fetch_stocktwits_messages outputs built" in output
    assert "get_fundamentals outputs built" in output
    assert "get_balance_sheet outputs built" in output
    assert "get_cashflow outputs built" in output
    assert "get_income_statement outputs built" in output
    assert "payloads_written: 4" in output
    assert "payloads_written: 2" in output
    with EvalDataset(dataset_path, read_only=True) as dataset:
        assert dataset.close_series("AAPL")
        assert dataset.close_series("SPY")
        assert dataset.tool_output("get_stock_data", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_stock_data", "SPY", "2026-01-03")
        assert dataset.tool_output("get_indicators", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_news", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_global_news", "AAPL", "2026-01-02")
        assert dataset.tool_output("fetch_reddit_posts", "AAPL", "2026-01-02")
        assert dataset.tool_output("fetch_stocktwits_messages", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_fundamentals", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_balance_sheet", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_cashflow", "AAPL", "2026-01-02")
        assert dataset.tool_output("get_income_statement", "AAPL", "2026-01-02")
