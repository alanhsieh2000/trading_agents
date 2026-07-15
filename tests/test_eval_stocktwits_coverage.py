"""Tests for the StockTwits raw coverage scanner."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from trading_agents.evaluation.stocktwits_coverage import (
    StocktwitsPage,
    _parse_cutoff,
    fetch_stocktwits_page,
    main,
    render_stage_result,
    scan_stage,
    scan_ticker_until_cutoff,
)


def _payload(
    ticker: str,
    *,
    since: int,
    max_id: int,
    more: bool,
    created_at: str,
) -> dict:
    return {
        "symbol": {"symbol": ticker},
        "cursor": {"more": more, "since": since, "max": max_id},
        "messages": [
            {
                "id": since,
                "created_at": created_at,
                "body": f"{ticker} message",
                "user": {"username": "tester"},
            }
        ],
    }


def _page(payload: dict) -> StocktwitsPage:
    return StocktwitsPage(
        payload=payload,
        content=json.dumps(payload).encode("utf-8"),
    )


def test_fetch_stocktwits_page_omits_max_for_first_page(monkeypatch):
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                _payload(
                    "AAPL",
                    since=10,
                    max_id=9,
                    more=False,
                    created_at="2026-01-02T00:00:00Z",
                )
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append((request.full_url, request.headers, timeout))
        return FakeResponse()

    monkeypatch.setattr(
        "trading_agents.evaluation.stocktwits_coverage.urlopen", fake_urlopen
    )

    page = fetch_stocktwits_page("aapl", timeout=3.0)

    assert page.payload["cursor"]["max"] == 9
    assert captured[0][0] == "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json"
    assert captured[0][2] == 3.0


def test_fetch_stocktwits_page_uses_max_for_next_page(monkeypatch):
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                _payload(
                    "AAPL",
                    since=9,
                    max_id=8,
                    more=False,
                    created_at="2026-01-01T00:00:00Z",
                )
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(
        "trading_agents.evaluation.stocktwits_coverage.urlopen", fake_urlopen
    )

    fetch_stocktwits_page("AAPL", max_id=9)

    assert captured == ["https://api.stocktwits.com/api/2/streams/symbol/AAPL.json?max=9"]


def test_scan_ticker_resumes_from_existing_cursor_and_sequence(tmp_path):
    existing = _payload(
        "AAPL",
        since=100,
        max_id=90,
        more=True,
        created_at="2026-07-13T00:00:00Z",
    )
    (tmp_path / "AAPL-0001.json").write_text(json.dumps(existing))
    calls = []

    def fake_fetch(ticker, *, max_id, timeout):
        calls.append((ticker, max_id, timeout))
        return _page(
            _payload(
                ticker,
                since=89,
                max_id=80,
                more=True,
                created_at="2025-12-17T23:59:00Z",
            )
        )

    result, made_request = scan_ticker_until_cutoff(
        ticker="aapl",
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=10,
        timeout=2,
        fetch_page=fake_fetch,
        sleep=lambda _seconds: None,
    )

    assert made_request is True
    assert calls == [("AAPL", 90, 2)]
    assert result.reached_cutoff is True
    assert result.files_written == (tmp_path / "AAPL-00002.json",)
    assert (tmp_path / "AAPL-00002.json").exists()


def test_scan_ticker_stops_when_cursor_more_false(tmp_path):
    calls = []

    def fake_fetch(ticker, *, max_id, timeout):
        calls.append((ticker, max_id))
        return _page(
            _payload(
                ticker,
                since=20,
                max_id=10,
                more=False,
                created_at="2026-01-01T00:00:00Z",
            )
        )

    result, _made_request = scan_ticker_until_cutoff(
        ticker="AMZN",
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=10,
        timeout=2,
        fetch_page=fake_fetch,
        sleep=lambda _seconds: None,
    )

    assert calls == [("AMZN", None)]
    assert result.cursor_more is False
    assert result.reached_cutoff is False
    assert result.files_written == (tmp_path / "AMZN-00001.json",)


def test_scan_ticker_sorts_existing_files_by_numeric_sequence(tmp_path):
    first = _payload(
        "AAPL",
        since=100,
        max_id=90,
        more=True,
        created_at="2026-07-13T00:00:00Z",
    )
    latest = _payload(
        "AAPL",
        since=10,
        max_id=5,
        more=True,
        created_at="2025-12-19T00:00:00Z",
    )
    (tmp_path / "AAPL-0001.json").write_text(json.dumps(first))
    (tmp_path / "AAPL-10000.json").write_text(json.dumps(latest))
    calls = []

    def fake_fetch(ticker, *, max_id, timeout):
        calls.append((ticker, max_id, timeout))
        return _page(
            _payload(
                ticker,
                since=4,
                max_id=1,
                more=True,
                created_at="2025-12-17T23:59:00Z",
            )
        )

    result, _made_request = scan_ticker_until_cutoff(
        ticker="AAPL",
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=0,
        timeout=2,
        fetch_page=fake_fetch,
        sleep=lambda _seconds: None,
    )

    assert calls == [("AAPL", 5, 2)]
    assert result.files_written == (tmp_path / "AAPL-10001.json",)


def test_scan_stage_waits_between_requests_including_between_tickers(tmp_path):
    calls = []
    sleeps = []
    pages = {
        "AAPL": [
            _payload(
                "AAPL",
                since=30,
                max_id=20,
                more=True,
                created_at="2026-01-01T00:00:00Z",
            ),
            _payload(
                "AAPL",
                since=19,
                max_id=10,
                more=True,
                created_at="2025-12-17T00:00:00Z",
            ),
        ],
        "GOOGL": [
            _payload(
                "GOOGL",
                since=40,
                max_id=30,
                more=True,
                created_at="2025-12-17T00:00:00Z",
            )
        ],
    }

    def fake_fetch(ticker, *, max_id, timeout):
        calls.append((ticker, max_id))
        return _page(pages[ticker].pop(0))

    result = scan_stage(
        name="Stage 1",
        tickers=("AAPL", "GOOGL"),
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=10,
        timeout=2,
        fetch_page=fake_fetch,
        sleep=sleeps.append,
    )

    assert calls == [("AAPL", None), ("AAPL", 20), ("GOOGL", None)]
    assert sleeps == [10, 10]
    assert result.succeeded is True


def test_scan_stage_honors_prior_request_from_previous_stage(tmp_path):
    sleeps = []

    result = scan_stage(
        name="Stage 2",
        tickers=("AAPL",),
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2023-12-18"),
        delay_seconds=10,
        timeout=2,
        fetch_page=lambda ticker, **_kwargs: _page(
            _payload(
                ticker,
                since=1,
                max_id=1,
                more=False,
                created_at="2023-12-17T00:00:00Z",
            )
        ),
        sleep=sleeps.append,
        made_prior_request=True,
    )

    assert sleeps == [10]
    assert result.succeeded is True


def test_scan_stage_caps_total_files_across_tickers(tmp_path):
    calls = []

    def fake_fetch(ticker, *, max_id, timeout):
        calls.append((ticker, max_id))
        sequence = len(calls)
        return _page(
            _payload(
                ticker,
                since=100 - sequence,
                max_id=90 - sequence,
                more=True,
                created_at="2026-01-01T00:00:00Z",
            )
        )

    result = scan_stage(
        name="Stage 1",
        tickers=("AAPL", "GOOGL"),
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=0,
        timeout=2,
        fetch_page=fake_fetch,
        sleep=lambda _seconds: None,
        max_files=3,
    )

    assert calls == [("AAPL", None), ("AAPL", 89), ("AAPL", 88)]
    assert len(result.tickers) == 1
    assert len(result.tickers[0].files_written) == 3


def test_scan_stage_does_not_fetch_when_existing_files_reach_cutoff(tmp_path):
    existing = _payload(
        "AAPL",
        since=100,
        max_id=90,
        more=True,
        created_at="2025-12-17T00:00:00Z",
    )
    (tmp_path / "AAPL-0001.json").write_text(json.dumps(existing))

    result = scan_stage(
        name="Stage 1",
        tickers=("AAPL",),
        output_dir=tmp_path,
        cutoff=_parse_cutoff("2025-12-18"),
        delay_seconds=10,
        timeout=2,
        fetch_page=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no fetch")),
        sleep=lambda _seconds: None,
    )

    assert result.succeeded is True
    assert result.tickers[0].files_written == ()


def test_render_stage_result_includes_status(tmp_path):
    result = scan_stage(
        name="Stage 1",
        tickers=("AAPL",),
        output_dir=tmp_path,
        cutoff=datetime(2025, 12, 18, tzinfo=timezone.utc),
        delay_seconds=0,
        timeout=2,
        fetch_page=lambda ticker, **_kwargs: _page(
            _payload(
                ticker,
                since=1,
                max_id=1,
                more=False,
                created_at="2025-12-17T00:00:00Z",
            )
        ),
        sleep=lambda _seconds: None,
    )

    output = render_stage_result(result)

    assert "Stage 1 StockTwits coverage scan" in output
    assert "succeeded: True" in output
    assert "AAPL files_written=1" in output


def test_main_defaults_to_one_second_delay_and_100_files(monkeypatch, tmp_path, capsys):
    captured = []

    def fake_scan_stage(**kwargs):
        captured.append(kwargs)
        return type(
            "Result",
            (),
            {
                "name": kwargs["name"],
                "cutoff": kwargs["cutoff"],
                "tickers": (),
                "succeeded": False,
            },
        )()

    monkeypatch.setattr(
        "trading_agents.evaluation.stocktwits_coverage.scan_stage", fake_scan_stage
    )

    exit_code = main(["--stage1-only", "--tickers", "AAPL", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert captured[0]["delay_seconds"] == 1.0
    assert captured[0]["max_files"] == 100
    output = capsys.readouterr().out
    assert output.startswith("It may take 132 seconds.")
    assert "Stage 1 StockTwits coverage scan" in output


def test_main_passes_max_files(monkeypatch, tmp_path):
    captured = []

    def fake_scan_stage(**kwargs):
        captured.append(kwargs)
        return type(
            "Result",
            (),
            {
                "name": kwargs["name"],
                "cutoff": kwargs["cutoff"],
                "tickers": (),
                "succeeded": False,
            },
        )()

    monkeypatch.setattr(
        "trading_agents.evaluation.stocktwits_coverage.scan_stage", fake_scan_stage
    )

    exit_code = main(
        [
            "--stage1-only",
            "--tickers",
            "AAPL",
            "--output-dir",
            str(tmp_path),
            "--max-files",
            "25",
        ]
    )

    assert exit_code == 1
    assert captured[0]["max_files"] == 25
