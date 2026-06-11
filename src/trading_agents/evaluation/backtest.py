"""Pure exchange simulator and cumulative-return (CR) math for the evaluation.

These functions implement the README "Backtest" rules exactly and perform no
I/O, so they are unit-testable without any network or language-model calls.

Decision ratings are one of ``Buy``, ``Overweight``, ``Hold``, ``Underweight``,
``Sell``. The simulated *position* is a fraction in ``[0, 1]``. Profit uses
average-cost accounting: raising the position updates the average cost of the
held units; reducing it realizes profit on the sold units at
``sell_price - avg_cost``. A forced ``Sell`` on the last trading day flattens
any remaining position so all profit is realized.

Cumulative return (per the README):

    CR = total_trading_profit / V_start * 100%

where ``V_start = max(close_at_first_Buy, close_at_first_Overweight / weight_over)``,
or ``1`` if neither a Buy nor an Overweight decision was ever made.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_VALID_RATINGS = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}


@dataclass
class BacktestResult:
    """Outcome of simulating one instrument's decision sequence."""

    total_profit: float = 0.0
    final_position: float = 0.0
    first_buy_date: str | None = None
    first_buy_close: float | None = None
    first_overweight_date: str | None = None
    first_overweight_close: float | None = None
    # One ``(date, rating, price, position_after, realized_delta)`` per applied
    # step, including the forced final Sell (rating ``"Sell*"``).
    steps: list[tuple[str, str, float, float, float]] = field(default_factory=list)


def _normalize_rating(rating: object) -> str:
    text = str(getattr(rating, "value", rating)).strip()
    canonical = text.capitalize()
    if canonical not in _VALID_RATINGS:
        raise ValueError(f"Unknown decision rating: {rating!r}")
    return canonical


def simulate_position(
    decisions: list[tuple[str, object]],
    closes: dict[str, float],
    weight_over: float,
    weight_under: float,
) -> BacktestResult:
    """Walk a chronological ``(date, rating)`` decision list and apply the rules.

    ``closes`` maps each decision date to that day's close (the transaction
    price). Raises ``KeyError`` if a decision date has no close price.
    """
    result = BacktestResult()
    position = 0.0
    avg_cost = 0.0

    def raise_to(target: float, date: str, price: float, rating: str) -> None:
        nonlocal position, avg_cost
        if target <= position:
            result.steps.append((date, rating, price, position, 0.0))
            return
        total_cost = position * avg_cost + (target - position) * price
        position = target
        avg_cost = total_cost / position
        result.steps.append((date, rating, price, position, 0.0))

    def reduce_to(target: float, date: str, price: float, rating: str) -> None:
        nonlocal position
        if position <= 0.0 or target >= position:
            result.steps.append((date, rating, price, position, 0.0))
            return
        sold = position - target
        realized = sold * (price - avg_cost)
        result.total_profit += realized
        position = target
        result.steps.append((date, rating, price, position, realized))

    last_date: str | None = None
    last_price: float | None = None
    for date, raw_rating in decisions:
        if date not in closes:
            raise KeyError(f"No close price for decision date {date!r}.")
        price = float(closes[date])
        rating = _normalize_rating(raw_rating)
        last_date, last_price = date, price

        if rating == "Buy":
            if result.first_buy_date is None:
                result.first_buy_date = date
                result.first_buy_close = price
            raise_to(1.0, date, price, rating)
        elif rating == "Overweight":
            if result.first_overweight_date is None:
                result.first_overweight_date = date
                result.first_overweight_close = price
            raise_to(weight_over, date, price, rating)
        elif rating == "Hold":
            result.steps.append((date, rating, price, position, 0.0))
        elif rating == "Underweight":
            reduce_to(weight_under, date, price, rating)
        elif rating == "Sell":
            reduce_to(0.0, date, price, rating)

    # Forced Sell on the last trading day to flatten any remaining position.
    if last_date is not None and last_price is not None and position > 0.0:
        reduce_to(0.0, last_date, last_price, "Sell*")

    result.final_position = position
    return result


def cumulative_return(result: BacktestResult, weight_over: float) -> float:
    """Return CR as a percentage, per the README definition of ``V_start``."""
    candidates: list[float] = []
    if result.first_buy_close is not None:
        candidates.append(result.first_buy_close)
    if result.first_overweight_close is not None and weight_over > 0:
        candidates.append(result.first_overweight_close / weight_over)
    v_start = max(candidates) if candidates else 1.0
    return result.total_profit / v_start * 100.0
