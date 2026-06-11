"""Evaluation package: the 2024-Q1 cumulative-return backtest.

See ``plans/07_evaluation_backtest.md``. This package is a record/replay
harness: a one-time builder records the analyst tools' outputs and daily close
prices into a committed DuckDB dataset, and an evaluation runner replays them
through the full TradingAgents flow in an offline "evaluation mode", then scores
the resulting daily decisions with an exchange simulator.
"""
