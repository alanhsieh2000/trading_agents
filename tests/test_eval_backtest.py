"""Tests for the pure exchange simulator and cumulative-return math."""

from __future__ import annotations

import math

import pytest

from trading_agents.evaluation.backtest import (
    BacktestResult,
    cumulative_return,
    simulate_position,
)

WEIGHT_OVER = 0.5
WEIGHT_UNDER = 0.5


def _cr(decisions, closes):
    result = simulate_position(decisions, closes, WEIGHT_OVER, WEIGHT_UNDER)
    return result, cumulative_return(result)


def test_buy_then_forced_sell_yields_simple_return():
    # Buy at 100, hold, forced Sell on the last day at 110 -> capital 10, V_start 100.
    decisions = [("2024-01-02", "Buy"), ("2024-01-03", "Hold"), ("2024-01-04", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 105.0, "2024-01-04": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.final_position == 0.0
    assert math.isclose(result.final_capital, 10.0)
    assert math.isclose(result.minimum_capital, -100.0)
    assert [step[4] for step in result.steps] == [-100.0, -100.0, -100.0, 10.0]
    assert math.isclose(cr, 10.0)


def test_hold_only_has_zero_capital_and_zero_cr():
    decisions = [("2024-01-02", "Hold"), ("2024-01-03", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.final_capital == 0.0
    assert result.minimum_capital == 0.0
    assert result.v_start == 0.0
    # No capital was deployed, so CR is defined as 0%.
    assert cr == 0.0


def test_sell_and_underweight_ignored_at_zero_position():
    decisions = [("2024-01-02", "Sell"), ("2024-01-03", "Underweight")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.final_capital == 0.0
    assert result.final_position == 0.0
    assert cr == 0.0


def test_overweight_raises_to_one_plus_weight_and_uses_minimum_capital():
    # Overweight raises to 1.5 at 100; forced Sell at 110 leaves capital 15.
    # V_start = 150, so CR = 15 / 150 * 100 = 10%.
    decisions = [("2024-01-02", "Overweight"), ("2024-01-03", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert math.isclose(result.minimum_capital, -150.0)
    assert math.isclose(result.v_start, 150.0)
    assert math.isclose(result.final_capital, 15.0)
    assert math.isclose(cr, 10.0)
    assert [step[3] for step in result.steps] == [1.5, 1.5, 0.0]


def test_capital_ledger_across_raises_and_reductions():
    # Buy 1 @ 100 -> -100; Overweight buys 0.5 @ 200 -> -200.
    # Underweight sells 1 @ 300 -> 100; forced Sell of 0.5 @ 300 -> 250.
    decisions = [
        ("2024-01-02", "Buy"),
        ("2024-01-03", "Overweight"),
        ("2024-01-04", "Underweight"),
    ]
    closes = {"2024-01-02": 100.0, "2024-01-03": 200.0, "2024-01-04": 300.0}
    result, cr = _cr(decisions, closes)
    assert math.isclose(result.minimum_capital, -200.0)
    assert math.isclose(result.final_capital, 250.0)
    assert result.final_position == 0.0
    assert [step[4] for step in result.steps] == [-100.0, -200.0, 100.0, 250.0]
    assert math.isclose(cr, 125.0)


def test_buy_when_already_full_is_noop():
    decisions = [("2024-01-02", "Buy"), ("2024-01-03", "Buy")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 100.0}
    result, _cr_value = _cr(decisions, closes)
    assert [step[4] for step in result.steps] == [-100.0, -100.0, 0.0]
    assert math.isclose(result.final_capital, 0.0)


def test_missing_close_raises():
    with pytest.raises(KeyError):
        simulate_position([("2024-01-02", "Buy")], {}, WEIGHT_OVER, WEIGHT_UNDER)


def test_unknown_rating_raises():
    with pytest.raises(ValueError):
        simulate_position(
            [("2024-01-02", "Maybe")], {"2024-01-02": 100.0}, WEIGHT_OVER, WEIGHT_UNDER
        )


def test_empty_decisions_is_zero_cr():
    result = simulate_position([], {}, WEIGHT_OVER, WEIGHT_UNDER)
    assert isinstance(result, BacktestResult)
    assert cumulative_return(result) == 0.0


@pytest.mark.parametrize(
    ("scale", "expected_v_start", "expected_final_capital", "expected_cr"),
    [
        (0.5, 150.0, 225.0, 150.0),
        (1.0, 200.0, 250.0, 125.0),
        (1.5, 250.0, 275.0, 110.0),
    ],
)
def test_scaled_weight_pairs_produce_distinct_results(
    scale, expected_v_start, expected_final_capital, expected_cr
):
    decisions = [
        ("2024-01-02", "Buy"),
        ("2024-01-03", "Overweight"),
        ("2024-01-04", "Underweight"),
    ]
    closes = {"2024-01-02": 100.0, "2024-01-03": 200.0, "2024-01-04": 300.0}

    result = simulate_position(
        decisions,
        closes,
        scale * WEIGHT_OVER,
        scale * WEIGHT_UNDER,
    )

    assert result.v_start == pytest.approx(expected_v_start)
    assert result.final_capital == pytest.approx(expected_final_capital)
    assert cumulative_return(result) == pytest.approx(expected_cr)
