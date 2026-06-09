"""Persistent lesson store and realized-return math for the Portfolio Crew.

A *lesson record* captures one past decision for one instrument. When the
portfolio manager next decides on the same instrument, prior records are
updated with their realized returns (raw return, alpha return) and holding
days, reflected on, and then retrieved as ``{lessons_line}``.

The return math is split into small pure functions that operate on already
fetched close-price series (a list of ``(date, close)`` tuples sorted
ascending). This keeps benchmark resolution, the holding-days cap, and the
``alpha_return = raw_return - benchmark_return`` rule fully testable without
any network access.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from trading_agents.config import BENCHMARK_MAP, get_settings
from trading_agents.schemas import LessonBook, LessonRecord


# A close-price series is a list of (date string, close price) tuples sorted by date.
CloseSeries = Sequence[tuple[str, float]]
# A fetcher maps a ticker to its close-price series at or after a trade date.
SeriesFetcher = Callable[[str, str], CloseSeries]

NO_LESSONS_LINE = "You have not invested this instrument in the past yet."


def resolve_benchmark(ticker: str, benchmark_map: dict[str, str] | None = None) -> str:
    """Resolve the benchmark index for a ticker from its exchange suffix."""
    mapping = benchmark_map if benchmark_map is not None else BENCHMARK_MAP
    symbol = str(ticker).strip().upper()
    if "." in symbol:
        suffix = "." + symbol.rsplit(".", 1)[1]
        for key, benchmark in mapping.items():
            if key and key.upper() == suffix:
                return benchmark
    return mapping.get("", "SPY")


def _index_on_or_before(dates: Sequence[str], target: str) -> int | None:
    """Return the index of the latest date <= target, or None if none exists."""
    found: int | None = None
    for index, date in enumerate(dates):
        if date <= target:
            found = index
        else:
            break
    return found


def transaction_days_after(series: CloseSeries, trade_date: str) -> int:
    """Count transaction days (CLOSE prices) strictly after the trade date."""
    dates = [date for date, _ in series]
    start = _index_on_or_before(dates, trade_date)
    if start is None:
        # No close on or before the trade date: every later close counts.
        return len(dates)
    return len(dates) - 1 - start


def compute_holding_days(
    instrument: CloseSeries,
    benchmark: CloseSeries,
    trade_date: str,
    max_holding_days: int,
) -> int:
    """Holding days = min(instrument days, benchmark days, max_holding_days).

    This is equivalent to the rule in PROMPTS.md / plan 06: if both the
    instrument and the benchmark already have more transaction days than
    ``max_holding_days`` since the trade date, holding days is capped at
    ``max_holding_days``; otherwise it is the smaller of the two counts.
    """
    instrument_days = transaction_days_after(instrument, trade_date)
    benchmark_days = transaction_days_after(benchmark, trade_date)
    return min(instrument_days, benchmark_days, max_holding_days)


def _close_to_close_return(series: CloseSeries, trade_date: str, holding_days: int) -> float:
    """Return (close[end] - close[start]) / close[start] for the series.

    ``start`` is the latest close on or before the trade date; ``end`` is the
    close exactly ``holding_days`` transaction days after ``start``.
    """
    dates = [date for date, _ in series]
    closes = [close for _, close in series]
    start = _index_on_or_before(dates, trade_date)
    if start is None:
        raise ValueError(f"No close price on or before trade date {trade_date}.")
    end = min(start + holding_days, len(closes) - 1)
    start_close = closes[start]
    if start_close == 0:
        raise ValueError("Trade-date close price is zero; cannot compute return.")
    return (closes[end] - start_close) / start_close


def compute_realized_metrics(
    instrument: CloseSeries,
    benchmark: CloseSeries,
    trade_date: str,
    max_holding_days: int,
) -> tuple[float, float, int]:
    """Compute (raw_return, alpha_return, holding_days) from price series.

    ``alpha_return = raw_return - benchmark_return``, where both returns use the
    close-to-close formula over the same ``holding_days`` window. If the
    benchmark has no close on the trade date, the latest previous available
    date is used as its start (handled by ``_index_on_or_before``).
    """
    holding_days = compute_holding_days(
        instrument, benchmark, trade_date, max_holding_days
    )
    raw_return = _close_to_close_return(instrument, trade_date, holding_days)
    benchmark_return = _close_to_close_return(benchmark, trade_date, holding_days)
    alpha_return = raw_return - benchmark_return
    return raw_return, alpha_return, holding_days


def format_return(value: float | None) -> str:
    """Render a return in +.1% format (for example, +2.3%)."""
    if value is None:
        return ""
    return f"{value:+.1%}"


def render_lessons_line(records: Sequence[LessonRecord]) -> str:
    """Render retrieved lesson records as ``{lessons_line}``.

    Falls back to the canonical no-history string when there are no records.
    """
    if not records:
        return NO_LESSONS_LINE

    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        lines = [
            f"Lesson {index}:",
            f"- Ticker: {record.ticker}",
            f"- Trade date: {record.trade_date}",
            f"- Final decision: {record.final_decision}",
            f"- Raw return: {format_return(record.raw_return) or 'pending'}",
            f"- Alpha return: {format_return(record.alpha_return) or 'pending'}",
            f"- Holding days: {record.holding_days if record.holding_days is not None else 'pending'}",
            f"- Reflection: {record.reflection or 'pending'}",
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class LessonStore:
    """JSON-backed lesson store keyed by instrument.

    Each instrument's records live in ``<base_dir>/<TICKER>.json`` as a
    serialized :class:`LessonBook`. Records are keyed by ``trade_date`` so
    reruns update existing rows in place rather than duplicating them.
    """

    def __init__(self, base_dir: str | Path = "output/lessons") -> None:
        self.base_dir = Path(base_dir)

    def _path(self, ticker: str) -> Path:
        return self.base_dir / f"{str(ticker).strip().upper()}.json"

    def load(self, ticker: str) -> LessonBook:
        path = self._path(ticker)
        if not path.exists():
            return LessonBook()
        return LessonBook.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, ticker: str, book: LessonBook) -> Path:
        path = self._path(ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(book.model_dump_json(indent=2), encoding="utf-8")
        return path

    def append(self, ticker: str, record: LessonRecord) -> LessonBook:
        """Append a record, replacing any existing record for the same trade date."""
        book = self.load(ticker)
        book.lessons = [
            existing
            for existing in book.lessons
            if existing.trade_date != record.trade_date
        ]
        book.lessons.append(record)
        self.save(ticker, book)
        return book


def update_records_with_returns(
    records: Sequence[LessonRecord],
    benchmark_name: str,
    fetch_series: SeriesFetcher,
    max_holding_days: int | None = None,
) -> list[LessonRecord]:
    """Update each record in place with realized returns and holding days.

    ``fetch_series(symbol, trade_date)`` must return that symbol's close-price
    series covering the holding window. Records whose returns cannot be
    computed (insufficient price data) are left unchanged.
    """
    if max_holding_days is None:
        max_holding_days = get_settings().portfolio_stage.max_holding_days

    updated: list[LessonRecord] = []
    for record in records:
        try:
            instrument = fetch_series(record.ticker, record.trade_date)
            benchmark = fetch_series(benchmark_name, record.trade_date)
            raw_return, alpha_return, holding_days = compute_realized_metrics(
                instrument, benchmark, record.trade_date, max_holding_days
            )
        except (ValueError, IndexError):
            continue
        record.raw_return = raw_return
        record.alpha_return = alpha_return
        record.holding_days = holding_days
        updated.append(record)
    return updated


def default_fetch_series(symbol: str, trade_date: str) -> list[tuple[str, float]]:
    """Fetch a close-price series for ``symbol`` from ``trade_date`` to now.

    Uses the existing market-data normalization so the same yfinance handling
    is shared with the analyst tools. Returns ``(date, close)`` tuples sorted
    ascending; an empty list when no price data is available.
    """
    from datetime import UTC, datetime, timedelta

    import yfinance as yf

    from trading_agents.tools.market_data import _normalise_price_history

    end_date = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        history = yf.download(
            str(symbol).strip(),
            start=trade_date,
            end=end_date,
            progress=False,
            auto_adjust=False,
        )
    except Exception:
        return []

    if history is None or history.empty:
        return []

    prices = _normalise_price_history(history, str(symbol).strip())
    if prices.empty or "close" not in prices.columns:
        return []

    series: list[tuple[str, float]] = []
    for _, row in prices.iterrows():
        close = row["close"]
        if close is None:
            continue
        try:
            series.append((str(row["date"]), float(close)))
        except (TypeError, ValueError):
            continue
    series.sort(key=lambda item: item[0])
    return series
