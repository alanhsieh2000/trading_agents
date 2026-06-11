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
    return result, cumulative_return(result, WEIGHT_OVER)


def test_buy_then_forced_sell_yields_simple_return():
    # Buy at 100, hold, forced Sell on the last day at 110 -> profit 10, V_start 100.
    decisions = [("2024-01-02", "Buy"), ("2024-01-03", "Hold"), ("2024-01-04", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 105.0, "2024-01-04": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.final_position == 0.0
    assert math.isclose(result.total_profit, 10.0)
    assert math.isclose(cr, 10.0)


def test_hold_only_uses_v_start_one_and_zero_profit():
    decisions = [("2024-01-02", "Hold"), ("2024-01-03", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.total_profit == 0.0
    assert result.first_buy_close is None and result.first_overweight_close is None
    # V_start = 1, profit = 0 -> CR = 0%.
    assert cr == 0.0


def test_sell_and_underweight_ignored_at_zero_position():
    decisions = [("2024-01-02", "Sell"), ("2024-01-03", "Underweight")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert result.total_profit == 0.0
    assert result.final_position == 0.0
    assert cr == 0.0


def test_overweight_v_start_divides_by_weight():
    # Overweight raises to 0.5 at 100; forced Sell at 110 -> profit 0.5*10 = 5.
    # V_start = 100 / 0.5 = 200 -> CR = 5 / 200 * 100 = 2.5%.
    decisions = [("2024-01-02", "Overweight"), ("2024-01-03", "Hold")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 110.0}
    result, cr = _cr(decisions, closes)
    assert math.isclose(result.total_profit, 5.0)
    assert math.isclose(cr, 2.5)


def test_buy_dominates_v_start_when_both_present():
    # Overweight first at 100 (-> V_start candidate 200), then Buy at 50
    # (-> candidate 50). max picks 200.
    decisions = [("2024-01-02", "Overweight"), ("2024-01-03", "Buy")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 50.0}
    result, _cr_value = _cr(decisions, closes)
    assert result.first_overweight_close == 100.0
    assert result.first_buy_close == 50.0
    v_start_value = max(50.0, 100.0 / WEIGHT_OVER)
    assert math.isclose(v_start_value, 200.0)


def test_average_cost_accounting_across_raises_and_reductions():
    # Overweight to 0.5 @ 100, then Buy to 1.0 @ 200 -> avg cost = (0.5*100 + 0.5*200)/1 = 150.
    # Underweight to 0.5 @ 300 -> realize 0.5*(300-150) = 75.
    # Forced Sell remaining 0.5 @ 300 (last day) -> realize 0.5*(300-150) = 75. Total 150.
    decisions = [
        ("2024-01-02", "Overweight"),
        ("2024-01-03", "Buy"),
        ("2024-01-04", "Underweight"),
    ]
    closes = {"2024-01-02": 100.0, "2024-01-03": 200.0, "2024-01-04": 300.0}
    result, _cr_value = _cr(decisions, closes)
    assert math.isclose(result.total_profit, 150.0)
    assert result.final_position == 0.0


def test_buy_when_already_full_is_noop_but_counts_for_v_start():
    decisions = [("2024-01-02", "Buy"), ("2024-01-03", "Buy")]
    closes = {"2024-01-02": 100.0, "2024-01-03": 100.0}
    result, _cr_value = _cr(decisions, closes)
    # First Buy sets V_start; second Buy is a no-op (already at 1.0).
    assert result.first_buy_date == "2024-01-02"
    assert math.isclose(result.total_profit, 0.0)


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
    assert cumulative_return(result, WEIGHT_OVER) == 0.0
