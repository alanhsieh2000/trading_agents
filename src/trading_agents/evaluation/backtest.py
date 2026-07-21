"""Pure exchange simulator and cumulative-return (CR) math for the evaluation.

These functions implement the README "Backtest" rules exactly and perform no
I/O, so they are unit-testable without any network or language-model calls.

Decision ratings are one of ``Buy``, ``Overweight``, ``Hold``, ``Underweight``,
``Sell``. The simulated position ranges from zero through ``1 + weight_over``.
Capital starts at zero, decreases when position is purchased, and increases
when position is sold. A forced ``Sell`` on the last trading day flattens any
remaining position.

Cumulative return (per the README):

    CR = final_capital / V_start * 100%

where ``V_start = -minimum_capital``. CR is zero when no capital was deployed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_VALID_RATINGS = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}


@dataclass
class BacktestResult:
    """Outcome of simulating one instrument's decision sequence."""

    final_capital: float = 0.0
    minimum_capital: float = 0.0
    final_position: float = 0.0
    # One ``(date, rating, price, position_after, capital_after)`` per applied
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
    capital = 0.0

    def move_to(target: float, date: str, price: float, rating: str) -> None:
        nonlocal position, capital
        capital -= (target - position) * price
        position = target
        result.minimum_capital = min(result.minimum_capital, capital)
        result.steps.append((date, rating, price, position, capital))

    def record_noop(date: str, price: float, rating: str) -> None:
        result.steps.append((date, rating, price, position, capital))

    last_date: str | None = None
    last_price: float | None = None
    for date, raw_rating in decisions:
        if date not in closes:
            raise KeyError(f"No close price for decision date {date!r}.")
        price = float(closes[date])
        rating = _normalize_rating(raw_rating)
        last_date, last_price = date, price

        if rating == "Buy":
            if position < 1.0:
                move_to(1.0, date, price, rating)
            else:
                record_noop(date, price, rating)
        elif rating == "Overweight":
            target = 1.0 + weight_over
            if position < target:
                move_to(target, date, price, rating)
            else:
                record_noop(date, price, rating)
        elif rating == "Hold":
            record_noop(date, price, rating)
        elif rating == "Underweight":
            target = 1.0 - weight_under
            if position > target:
                move_to(target, date, price, rating)
            else:
                record_noop(date, price, rating)
        elif rating == "Sell":
            if position > 0.0:
                move_to(0.0, date, price, rating)
            else:
                record_noop(date, price, rating)

    # Forced Sell on the last trading day to flatten any remaining position.
    if last_date is not None and last_price is not None and position > 0.0:
        move_to(0.0, last_date, last_price, "Sell*")

    result.final_capital = capital
    result.final_position = position
    return result


def cumulative_return(result: BacktestResult) -> float:
    """Return CR as a percentage, per the README definition of ``V_start``."""
    v_start = -result.minimum_capital
    if v_start == 0.0:
        return 0.0
    return result.final_capital / v_start * 100.0
