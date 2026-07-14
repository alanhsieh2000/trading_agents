"""StockTwits pagination scanner for evaluation coverage checks."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from trading_agents.config import get_settings
from trading_agents.tools.sentiment import STOCKTWITS_HEADERS


DEFAULT_OUTPUT_DIR = Path("data/raw-backtest/stocktwits")
PLAN_B_CUTOFF = "2025-12-18"
PLAN_07_CUTOFF = "2023-12-18"


@dataclass(frozen=True)
class StocktwitsPage:
    payload: dict[str, Any]
    content: bytes


@dataclass(frozen=True)
class TickerScanResult:
    ticker: str
    files_written: tuple[Path, ...]
    newest_created_at: datetime | None
    oldest_created_at: datetime | None
    last_cursor_max: int | None
    cursor_more: bool
    reached_cutoff: bool
    next_sequence: int


@dataclass(frozen=True)
class StageScanResult:
    name: str
    cutoff: datetime
    tickers: tuple[TickerScanResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(result.reached_cutoff for result in self.tickers)


def fetch_stocktwits_page(
    ticker: str,
    *,
    max_id: int | None = None,
    timeout: float = 20.0,
) -> StocktwitsPage:
    """Fetch one StockTwits symbol-stream page."""
    symbol = ticker.upper().strip()
    query = "" if max_id is None else "?" + urlencode({"max": max_id})
    url = (
        f"https://api.stocktwits.com/api/2/streams/symbol/"
        f"{quote(symbol)}.json{query}"
    )
    request = Request(url, headers=STOCKTWITS_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"StockTwits response for {symbol} was not a JSON object")
    return StocktwitsPage(payload=payload, content=content)


def scan_stage(
    *,
    name: str,
    tickers: Sequence[str],
    output_dir: Path,
    cutoff: datetime,
    delay_seconds: float,
    timeout: float,
    fetch_page: Callable[..., StocktwitsPage] = fetch_stocktwits_page,
    sleep: Callable[[float], None] = time.sleep,
    made_prior_request: bool = False,
) -> StageScanResult:
    """Scan every ticker until the cutoff or StockTwits pagination ends."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[TickerScanResult] = []
    for ticker in tickers:
        result, made_prior_request = scan_ticker_until_cutoff(
            ticker=ticker,
            output_dir=output_dir,
            cutoff=cutoff,
            delay_seconds=delay_seconds,
            timeout=timeout,
            fetch_page=fetch_page,
            sleep=sleep,
            made_prior_request=made_prior_request,
        )
        results.append(result)
    return StageScanResult(name=name, cutoff=cutoff, tickers=tuple(results))


def scan_ticker_until_cutoff(
    *,
    ticker: str,
    output_dir: Path,
    cutoff: datetime,
    delay_seconds: float,
    timeout: float,
    fetch_page: Callable[..., StocktwitsPage] = fetch_stocktwits_page,
    sleep: Callable[[float], None] = time.sleep,
    made_prior_request: bool = False,
) -> tuple[TickerScanResult, bool]:
    """Continue one ticker's JSON sequence until coverage reaches ``cutoff``."""
    symbol = ticker.upper().strip()
    existing = sorted(output_dir.glob(f"{symbol}-*.json"))
    existing_summary = summarize_ticker_files(symbol, existing)
    next_sequence = _next_sequence(existing)
    max_id = existing_summary.last_cursor_max
    cursor_more = existing_summary.cursor_more
    newest = existing_summary.newest_created_at
    oldest = existing_summary.oldest_created_at
    written: list[Path] = []

    while cursor_more and not _reached_cutoff(oldest, cutoff):
        if made_prior_request and delay_seconds > 0:
            sleep(delay_seconds)
        page = fetch_page(symbol, max_id=max_id, timeout=timeout)
        made_prior_request = True
        path = _next_available_path(output_dir, symbol, next_sequence)
        _write_json_atomic(path, page.content)
        written.append(path)

        page_summary = summarize_payload(page.payload)
        newest = _min_none_aware(newest, page_summary.newest_created_at, newest=True)
        oldest = _min_none_aware(oldest, page_summary.oldest_created_at, newest=False)
        max_id = page_summary.last_cursor_max
        cursor_more = page_summary.cursor_more
        next_sequence = _sequence_from_path(path) + 1

    return (
        TickerScanResult(
            ticker=symbol,
            files_written=tuple(written),
            newest_created_at=newest,
            oldest_created_at=oldest,
            last_cursor_max=max_id,
            cursor_more=cursor_more,
            reached_cutoff=_reached_cutoff(oldest, cutoff),
            next_sequence=next_sequence,
        ),
        made_prior_request,
    )


def summarize_ticker_files(ticker: str, paths: Sequence[Path]) -> TickerScanResult:
    newest: datetime | None = None
    oldest: datetime | None = None
    last_cursor_max: int | None = None
    cursor_more = True
    next_sequence = 1
    for path in sorted(paths):
        payload = json.loads(path.read_text())
        summary = summarize_payload(payload)
        newest = _min_none_aware(newest, summary.newest_created_at, newest=True)
        oldest = _min_none_aware(oldest, summary.oldest_created_at, newest=False)
        last_cursor_max = summary.last_cursor_max
        cursor_more = summary.cursor_more
        next_sequence = max(next_sequence, _sequence_from_path(path) + 1)
    return TickerScanResult(
        ticker=ticker.upper().strip(),
        files_written=(),
        newest_created_at=newest,
        oldest_created_at=oldest,
        last_cursor_max=last_cursor_max,
        cursor_more=cursor_more,
        reached_cutoff=False,
        next_sequence=next_sequence,
    )


def summarize_payload(payload: dict[str, Any]) -> TickerScanResult:
    messages = payload.get("messages") if isinstance(payload, dict) else None
    timestamps = [
        parsed
        for message in messages or []
        if isinstance(message, dict)
        for parsed in [_parse_stocktwits_datetime(message.get("created_at"))]
        if parsed is not None
    ]
    cursor = payload.get("cursor") if isinstance(payload, dict) else {}
    cursor = cursor if isinstance(cursor, dict) else {}
    symbol_value = payload.get("symbol") if isinstance(payload, dict) else ""
    if isinstance(symbol_value, dict):
        ticker = str(symbol_value.get("symbol", "")).upper()
    else:
        ticker = str(symbol_value or "").upper()
    return TickerScanResult(
        ticker=ticker,
        files_written=(),
        newest_created_at=max(timestamps) if timestamps else None,
        oldest_created_at=min(timestamps) if timestamps else None,
        last_cursor_max=_as_int(cursor.get("max")),
        cursor_more=bool(cursor.get("more")),
        reached_cutoff=False,
        next_sequence=1,
    )


def render_stage_result(result: StageScanResult) -> str:
    lines = [
        f"{result.name} StockTwits coverage scan",
        f"cutoff: {result.cutoff.date().isoformat()}",
        f"succeeded: {result.succeeded}",
    ]
    for ticker_result in result.tickers:
        lines.append(
            " ".join(
                [
                    ticker_result.ticker,
                    f"files_written={len(ticker_result.files_written)}",
                    f"newest={_format_dt(ticker_result.newest_created_at)}",
                    f"oldest={_format_dt(ticker_result.oldest_created_at)}",
                    f"last_cursor_max={ticker_result.last_cursor_max}",
                    f"cursor_more={ticker_result.cursor_more}",
                    f"reached_cutoff={ticker_result.reached_cutoff}",
                ]
            )
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download raw StockTwits pages until evaluation coverage cutoffs."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tickers", nargs="+")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--stage1-cutoff", default=PLAN_B_CUTOFF)
    parser.add_argument("--stage2-cutoff", default=PLAN_07_CUTOFF)
    parser.add_argument("--stage1-only", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    tickers = tuple(
        ticker.upper() for ticker in (args.tickers or settings.evaluation.tickers)
    )
    output_dir = Path(args.output_dir)
    stage1 = scan_stage(
        name="Stage 1",
        tickers=tickers,
        output_dir=output_dir,
        cutoff=_parse_cutoff(args.stage1_cutoff),
        delay_seconds=max(args.delay, 0.0),
        timeout=args.timeout,
    )
    print(render_stage_result(stage1))
    if args.stage1_only or not stage1.succeeded:
        return 0 if stage1.succeeded else 1

    stage1_made_request = any(result.files_written for result in stage1.tickers)
    stage2 = scan_stage(
        name="Stage 2",
        tickers=tickers,
        output_dir=output_dir,
        cutoff=_parse_cutoff(args.stage2_cutoff),
        delay_seconds=max(args.delay, 0.0),
        timeout=args.timeout,
        made_prior_request=stage1_made_request,
    )
    print()
    print(render_stage_result(stage2))
    return 0 if stage2.succeeded else 1


def _write_json_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _next_available_path(output_dir: Path, ticker: str, sequence: int) -> Path:
    path = output_dir / f"{ticker}-{sequence:04d}.json"
    while path.exists():
        sequence += 1
        path = output_dir / f"{ticker}-{sequence:04d}.json"
    return path


def _next_sequence(paths: Sequence[Path]) -> int:
    sequences = [_sequence_from_path(path) for path in paths]
    return max(sequences, default=0) + 1


def _sequence_from_path(path: Path) -> int:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _parse_cutoff(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc)


def _parse_stocktwits_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reached_cutoff(oldest: datetime | None, cutoff: datetime) -> bool:
    return oldest is not None and oldest <= cutoff


def _min_none_aware(
    current: datetime | None, candidate: datetime | None, *, newest: bool
) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate) if newest else min(current, candidate)


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
