# TradingAgents v1.0.0

Released: 2026-07-27

TradingAgents v1.0.0 is the first major release of the CrewAI-based
reimplementation of the TradingAgents multi-agent financial trading framework.
It delivers an end-to-end workflow that turns market data into a structured
portfolio decision and includes a reproducible evaluation and backtesting
toolchain.

## Highlights

- Complete five-stage CrewAI flow: analyst, research, trader, risk management,
  and portfolio management.
- Specialized bullish, bearish, aggressive, conservative, and neutral debate
  roles with configurable debate rounds.
- Structured Pydantic contracts for investment plans, trader proposals, final
  portfolio decisions, and historical lesson records.
- Market, technical-indicator, news, fundamentals, financial-statement, Reddit,
  and StockTwits data integrations.
- Persistent portfolio lessons with realized-return and benchmark-relative
  reflection.
- Configurable quick and deep LLM roles, including OpenAI, Anthropic, Azure, and
  Gemini-compatible CrewAI providers.
- DuckDB-backed record/replay evaluation with resumable execution, request
  quotas, and multi-scenario backtesting.

## Trading Workflow

The release runs five crews in sequence:

1. The Analyst Crew produces market, sentiment, news, and fundamentals reports.
2. The Research Crew debates the bull and bear cases and creates a structured
   investment plan.
3. The Trader Crew converts the plan into a `Buy`, `Hold`, or `Sell` proposal
   with optional entry, stop-loss, and sizing guidance.
4. The Risk Management Crew reviews the proposal from aggressive,
   conservative, and neutral perspectives.
5. The Portfolio Crew returns a final `Buy`, `Overweight`, `Hold`,
   `Underweight`, or `Sell` rating with an executive summary, investment thesis,
   and optional price target and time horizon.

Run the flow for a ticker and trade date:

```bash
uv sync
uv run analyze --ticker AAPL --trade-date 2026-07-27
```

Omitting `--trade-date` uses the current UTC date. Omitting both arguments uses
the default ticker, `NVDA`, and the current UTC date.

Each run writes its reports to `output/<TICKER>_<TRADE_DATE>/`, including the
four analyst reports, research debate, investment plan, trader plan, risk
debate, and final trade decision.

## Evaluation and Backtesting

v1.0.0 includes a prepared-data evaluation framework modeled on the original
paper's AAPL, GOOGL, and AMZN evaluation over 2024-01-01 through 2024-03-29.
Analyst tool responses and prices can be recorded in DuckDB and replayed without
live data calls during evaluation.

The evaluation runner:

- checkpoints every completed decision and resumes compatible runs;
- enforces per-minute and daily request budgets for quick and deep LLMs;
- preserves quota usage when decision progress is restarted;
- simulates 0.5x, 1.0x, and 1.5x overweight/underweight scenarios; and
- writes `evaluation_report.md` and `evaluation_results.csv`.

Run a short evaluation smoke test:

```bash
uv run run-eval --limit-days 1
```

A compatible DuckDB dataset must exist at the configured evaluation dataset
path. Evaluation datasets and generated outputs are local artifacts and are not
tracked by Git.

## Configuration

Runtime settings use typed defaults and `TRADING_AGENTS_` environment variables.
Frequently used settings include:

- `TRADING_AGENTS_LLM__QUICK_LLM`
- `TRADING_AGENTS_LLM__DEEP_LLM`
- `TRADING_AGENTS_RESEARCH_STAGE__MAX_ROUNDS`
- `TRADING_AGENTS_RISK_STAGE__MAX_ROUNDS`
- `TRADING_AGENTS_EVALUATION__DATASET_PATH`
- `TRADING_AGENTS_EVALUATION__MAX_RPM`
- `TRADING_AGENTS_EVALUATION__DAILY_REQUEST_BUDGET`

Set the API key required by the selected LLM provider in `.env`. Live data and
dataset-building workflows may also require provider credentials such as
`EXA_API_KEY`.

## Requirements

- Python 3.12 or 3.13
- `uv` for dependency and command management
- CrewAI 1.15.6 or later
- Network access and valid provider credentials for live analysis

## Notes

- Model output and third-party market data can be incomplete, delayed, or
  inconsistent. Review generated decisions and source data before relying on
  them.
- This project is a research and evaluation implementation. It does not execute
  brokerage orders and does not provide financial advice.
- This release is a CrewAI reimplementation inspired by the original
  TradingAgents project, not a line-by-line port.

## Acknowledgements

TradingAgents is based on the architecture described by Yijia Xiao, Edward Sun,
Di Luo, and Wei Wang in *TradingAgents: Multi-Agents LLM Financial Trading
Framework* (arXiv:2412.20138), and on the open-source implementation by Tauric
Research.
