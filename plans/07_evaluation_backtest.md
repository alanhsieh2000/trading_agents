# Build the TradingAgents Evaluation: a 2024-Q1 Cumulative-Return Backtest (Plan 07)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.


## Purpose / Big Picture

After this change, a user can measure how well the TradingAgents system actually
trades, by reproducing the evaluation in the README's `# Evaluation` section (which
follows the paper *TradingAgents: Multi-Agents LLM Financial Trading Framework*,
section 6.1, Table 1). The system makes a daily decision — one of `Buy`,
`Overweight`, `Hold`, `Underweight`, or `Sell` — for three stocks (AAPL, GOOGL,
AMZN) on every trading day from 2024-01-01 through 2024-03-29. A simple exchange
simulator turns those decisions into positions and profit, and the run reports the
**cumulative return (CR)** for each stock.

Concretely, after this plan a user runs two commands from the project root:

    uv run build-eval-dataset
    uv run run-eval

and sees a report such as:

    TradingAgents evaluation — 2024-01-01..2024-03-29 (61 trading days)
    AAPL   CR = +4.2%
    GOOGL  CR = +9.1%
    AMZN   CR = +12.7%

The hard part this plan solves is **data**. The agents need news, social sentiment,
prices, indicators, and fundamentals *as they were during 2024-Q1*. Some of those
sources cannot be queried for an arbitrary past window (see "Data availability"
below). So the first command **builds a prepared dataset** of recorded tool outputs
into a committed DuckDB file, and the second command runs the agents in an
**evaluation mode** that reads from that dataset instead of calling live APIs. This
makes the evaluation reproducible and offline (apart from the language-model calls).


## Progress

- [x] (2026-06-11) Added `EvaluationSettings` to `src/trading_agents/config/settings.py`, wired it into `AppSettings`, and exported it from `config/__init__.py`.
- [x] (2026-06-12 05:55Z) Added `exa-py` usage and an `EXA_API_KEY` requirement; created `src/trading_agents/evaluation/exa_sources.py` with historical news, global-news, Reddit, and StockTwits helpers plus unit tests.
- [x] (2026-06-11) Created `src/trading_agents/evaluation/dataset.py` (DuckDB-backed `EvalDataset`, `tool_outputs` + `prices` tables, idempotent upserts).
- [ ] (pending) Create the `build-eval-dataset` entry point with an early historical-source availability gate in `src/trading_agents/evaluation/build_dataset.py`; the gate must run before DuckDB writes and fail fast if required Exa sources are unavailable for the configured period.
- [ ] (pending) Implement the DuckDB dataset build phase in `build_dataset.py` after the availability gate passes: prices, market data, indicators, Exa news/global news/Reddit/StockTwits, and fundamentals/statement tool outputs.
- [ ] (pending) If the availability gate fails for the configured 2024-Q1 evaluation, scan candidate replacement periods and record findings before building any dataset.
- [x] (2026-06-11) Created `src/trading_agents/evaluation/eval_tools.py` (dataset-backed `DatasetBackedTool` + `build_dataset_tools`). Remaining: the analyst-crew tool-injection seam.
- [x] (2026-06-11) Created `src/trading_agents/evaluation/backtest.py` (`simulate_position` + `cumulative_return`).
- [ ] (pending) Create `src/trading_agents/evaluation/run_eval.py` and the `run-eval` entry point.
- [x] (2026-06-11) Added unit tests `tests/test_eval_backtest.py` (10) and `tests/test_eval_dataset.py` (7); all pass, full suite 113 passed with no regressions.
- [ ] (pending) Build the committed dataset `data/eval_dataset.duckdb` and run a smoke evaluation.
- [ ] (pending) Run the full evaluation and record CR per stock in `Outcomes & Retrospective`.

Use timestamps (for example `(2026-06-11 09:00Z)`) when checking items off so a
future contributor can gauge the rate of progress.


## Surprises & Discoveries

- Observation: yfinance cannot return historical news or social posts for a past
  window. `yf.Ticker(symbol).news` returns only Yahoo's *current* feed; the
  `start_date`/`end_date` arguments in `get_news`/`get_global_news` merely
  client-side-filter that current feed.
  Evidence: `src/trading_agents/tools/news.py` builds `items = list(getattr(yf.Ticker(clean_query), "news", None) or [])` and then filters by date; there is no historical query. Confirmed against the yfinance docs and issue tracker.
- Observation: Reddit and StockTwits fetchers are recent-only.
  Evidence: `src/trading_agents/tools/sentiment.py` queries `reddit.com/r/{sub}/search.json?...&t=week` and StockTwits `streams/symbol/{symbol}.json`, and filters Reddit posts against `now - recency_window_seconds`. Neither endpoint accepts a historical range.
- Observation: The current live `fetch_reddit_posts` tool can mask Reddit API
  blocking as ordinary missing data.
  Evidence: On 2026-06-15, the underlying endpoint
  `https://www.reddit.com/r/wallstreetbets/search.json?q=AAPL&restrict_sr=on&sort=new&t=week&limit=5`
  returned `HTTPError 403 Blocked` in this environment, while
  `fetch_reddit_posts("AAPL", subreddits=("wallstreetbets",), ...)` returned
  `No data available for Reddit posts for AAPL.` because `_fetch_subreddit_posts()`
  exceptions are caught and converted to an empty post list. Therefore, the current
  fallback string does not distinguish true zero results from blocked or failed
  Reddit access.
- Observation: `exa-py` is already a declared dependency but is unused in the
  codebase, and Exa's search API supports `start_published_date`/`end_published_date`.
  Evidence: `pyproject.toml` lists `exa-py>=2.13.0`; a repository-wide grep finds no import of it. Exa's `/search` documents published-date filters for the `news` category and for uncategorized searches.
- Observation: The installed `exa-py` API surface directly supports the evaluation
  source helpers without a wrapper dependency.
  Evidence: `uv run python -c "import inspect; from exa_py import Exa; print(inspect.signature(Exa.search))"` shows `start_published_date`, `end_published_date`, `include_domains`, `category`, and `num_results` keyword parameters. The unit tests monkeypatch `Exa.search` and verify the news, Reddit, and StockTwits helpers pass those arguments.
- Observation: A live Exa probe for the earliest buffer window found ticker news,
  global news, and StockTwits data for 2023-12-01 through 2023-12-10, but no Reddit
  data for AAPL, GOOGL, or AMZN.
  Evidence: `uv run python - <<'PY' ... Exa.search(... start_published_date='2023-12-01', end_published_date='2023-12-10' ...) ... PY` returned 3 results each for AAPL/GOOGL/AMZN news, 3 for global news, and 3 each for StockTwits, while AAPL/GOOGL/AMZN Reddit domain searches returned 0. Follow-up Reddit-only probes for 2024-01-02..2024-01-12, 2024-03-18..2024-03-28, and undated Reddit searches also returned 0, so Reddit is the likely data-availability blocker.
- Observation: 2024-03-29 is Good Friday, when US markets are closed, so the real
  last trading day in the window is 2024-03-28. The window nonetheless holds exactly
  **61 trading days** (2024-01-02 .. 2024-03-28), matching the README's "61 transaction
  days".
  Evidence: `uv run python -c "import yfinance as yf; print(len(yf.download('AAPL', start='2024-01-01', end='2024-03-30', progress=False, auto_adjust=False)))"` returns `61`; first row 2024-01-02, last 2024-03-28, and 2024-03-29 is absent (holiday).

Add new observations here as they arise, with a short evidence snippet (test output
is ideal).


## Decision Log

- Decision: Split the evaluation out of the end-to-end-flow ExecPlan (now
  `plans/08_end_to_end_flow.md`) into this plan, and push that plan's evaluation scope
  back.
  Rationale: The evaluation needs a prepared historical dataset, an evaluation
  execution mode, an exchange simulator, and an orchestration runner — far more than
  the single "evaluation checks" bullet that plan carried. The end-to-end-flow plan
  remains focused on wiring the flow.
  Date/Author: 2026-06-11 / Claude

- Decision: Swap the plan numbers so this evaluation ExecPlan is **plan 07** and the
  already-implemented end-to-end-flow ExecPlan is **plan 08**
  (`plans/08_end_to_end_flow.md`).
  Rationale: The user wants the next-to-implement work (evaluation) to carry the
  active plan number. The flow is already implemented, so the dependency-order
  inversion (evaluation logically builds on the flow) is moot in practice.
  Date/Author: 2026-06-11 / Claude (confirmed with the user)

- Decision: Use a record/replay design — a one-time dataset build, then offline
  evaluation runs that read recorded tool outputs.
  Rationale: The README mandates a prepared dataset because several sources cannot be
  queried historically; record/replay also makes the 3-stock × 61-day evaluation
  deterministic and cheap to re-run (only language-model calls remain live).
  Date/Author: 2026-06-11 / Claude

- Decision: Source historical news and social sentiment from Exa with published-date
  filters (`EXA_API_KEY` required); store the prepared dataset as a single committed
  DuckDB file under `data/`.
  Rationale: `exa-py` is already a dependency and Exa supports historical date
  filtering; Finnhub's free tier only covers ~1 year of history, which cannot reach
  2024 from 2026. DuckDB (`duckdb` is already a dependency) gives a single,
  query-friendly, committable artifact.
  Date/Author: 2026-06-11 / Claude (confirmed with the user)

- Decision: The portfolio crew is not modified; the evaluation passes a
  dataset-backed `fetch_series` into `run_portfolio_stage`.
  Rationale: `run_portfolio_stage` already accepts a `fetch_series` parameter, so the
  realized-return math can read recorded prices without touching the crew.
  Date/Author: 2026-06-11 / Claude

- Decision: Implement the offline, no-API-key pieces first (settings, `EvalDataset`,
  the backtest simulator, `eval_tools`, and their unit tests) as Milestone 1, before
  the Exa sources / builder / runner that need credentials and live calls.
  Rationale: This delivers a deterministic, fully testable core that can be committed
  and reviewed independently, and de-risks the README backtest math before any
  expensive language-model or network work.
  Date/Author: 2026-06-11 / Claude

- Decision: Treat historical Reddit data as required for the prepared evaluation
  dataset and make source availability verification the first phase of
  `build-eval-dataset`.
  Rationale: The README evaluation lists Reddit among the analyst data sources, and the
  user confirmed that missing Reddit should not be silently accepted. A live Exa probe
  found no Reddit results for the earliest buffer window or sampled Q1 windows, so the
  builder must fail before DuckDB writes if required sources are unavailable.
  Date/Author: 2026-06-12 / Codex (confirmed with the user)

- Decision: The evaluation dataset builder must record Reddit probe status separately
  from Reddit result count.
  Rationale: `No data available for Reddit posts ...` is ambiguous in the current live
  tool: it can mean zero matching posts, HTTP 403 blocking, timeout, JSON parse
  failure, or another network error. Plan 07's availability gate needs structured
  statuses such as `ok`, `empty`, `blocked`, `timeout`, and `parse_error` so it fails
  for source access problems instead of misclassifying them as empty data.
  Date/Author: 2026-06-15 / Codex

Record every further decision here, with the reasoning, as the plan evolves.


## Outcomes & Retrospective

Milestone 1 — Offline foundation (2026-06-11). Delivered the deterministic, no-API-key
core of the evaluation and verified it end-to-end:

- `EvaluationSettings` added to `src/trading_agents/config/settings.py`, wired into
  `AppSettings` as `evaluation`, and exported from `config/__init__.py`.
- `src/trading_agents/evaluation/dataset.py` — `EvalDataset` over DuckDB with the
  `tool_outputs` and `prices` tables, idempotent `INSERT OR REPLACE` upserts, a loud
  `KeyError` when a recorded row is missing, and `transaction_days()` /
  `close_series()` readers.
- `src/trading_agents/evaluation/backtest.py` — pure `simulate_position` and
  `cumulative_return` implementing the README rules (average-cost accounting, forced
  final Sell, `V_start = max(first-Buy close, first-Overweight close / weight_over)`,
  else 1).
- `src/trading_agents/evaluation/eval_tools.py` — `DatasetBackedTool` and
  `build_dataset_tools` (the analyst-crew injection seam that consumes them is still
  pending).
- Tests `tests/test_eval_backtest.py` (10) and `tests/test_eval_dataset.py` (7) pass;
  the full suite is **113 passed** with no regressions.

What remains from the original evaluation plan: the analyst-crew evaluation seam, the
`build-eval-dataset` and `run-eval` entry points, building the committed
`data/eval_dataset.duckdb`, and the full evaluation that produces CR per stock (to be
compared with the paper's Table 1 and recorded here). Building the dataset requires an
`EXA_API_KEY`.

Lessons so far: the README's "61 transaction days" is exactly right (verified against
yfinance) — the earlier "~60 / Good Friday discrepancy" worry was unfounded.

Milestone 2 — Exa source layer (2026-06-12 05:55Z). Delivered the historical
news/social source helpers that the dataset builder will call:

- `src/trading_agents/evaluation/exa_sources.py` loads `.env`, requires `EXA_API_KEY`,
  constructs an `exa_py.Exa` client, and exposes helpers for ticker news, global market
  news, Reddit, and StockTwits.
- The helpers use Exa published-date filters, render news via the existing
  `_format_news_block` style, and return the existing sentiment fallback strings when no
  historical social results are found.
- Tests `tests/test_eval_exa_sources.py` (6) pass with mocked Exa calls; the focused
  evaluation suite is now **23 passed** across Exa sources, dataset, and backtest.

What remains after this milestone: create `build_dataset.py` and the
`build-eval-dataset` entry point so these Exa helpers can populate the DuckDB dataset.

Milestone 3 — Source availability gate (planned next). The next implementation must
make `build-eval-dataset` verify historical source availability before creating or
updating the DuckDB dataset. The gate checks the earliest risky buffer window first
(currently 2023-12-01 through 2023-12-10) for ticker news, global news, Reddit, and
StockTwits. If any required source is unavailable, especially Reddit, the command exits
nonzero with a compact source-by-source report and leaves the dataset untouched. Only
after this gate passes should the builder download prices and record tool outputs.


## Context and Orientation

This section assumes no prior knowledge of the repository. Read it before editing.

The project is a CrewAI reimplementation of TradingAgents. A *crew* is a team of
language-model agents that run *tasks* in order; a *flow* chains crews together. The
end-to-end flow lives in `src/trading_agents/main.py` as `TradingAgentsFlow`, which
runs five stages in sequence and returns a final structured decision:

1. Analyst stage — `run_analyst_stage` in `src/trading_agents/crews/analyst_crew/analyst_crew.py`. Produces four text reports (market, sentiment, news, fundamentals). **This is the only stage that calls external data sources.**
2. Research stage — `run_research_stage` in `src/trading_agents/crews/research_crew/research_crew.py`.
3. Trader stage — `run_trader_stage` in `src/trading_agents/crews/trader_crew/trader_crew.py`.
4. Risk stage — `run_risk_stage` in `src/trading_agents/crews/risk_management_crew/risk_management_crew.py`.
5. Portfolio stage — `run_portfolio_stage` in `src/trading_agents/crews/portfolio_crew/portfolio_crew.py`. Returns a `PortfolioDecision` whose `rating` is exactly one of `Buy`, `Overweight`, `Hold`, `Underweight`, `Sell` (defined in `src/trading_agents/schemas.py`).

The flow takes a *trigger payload* — a small dictionary with `ticker` and
`trade_date` (a date string in `YYYY-MM-DD` form) — and threads those plus each
stage's output into the next stage.

The ten data tools used by the analyst stage are:

- `get_stock_data`, `get_indicators` in `src/trading_agents/tools/market_data.py` (the underlying functions are `get_stock_data_text(ticker, start_date, end_date)` and `get_indicators_text(ticker, start_date, end_date, indicators)`; both use `yf.download`).
- `get_news`, `get_global_news` in `src/trading_agents/tools/news.py` (use `yf.Ticker(...).news`; the helper `_format_news_block(heading, records)` renders the output text).
- `fetch_reddit_posts`, `fetch_stocktwits_messages` in `src/trading_agents/tools/sentiment.py` (plain functions, not CrewAI tools; they hit Reddit and StockTwits HTTP endpoints).
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` in `src/trading_agents/tools/fundamentals.py` (use `yf.Ticker(...).info` and the financial-statement attributes).

How the analyst stage assembles its inputs is important for the evaluation seam.
`prepare_analyst_inputs(inputs)` in `analyst_crew.py`:

- normalizes `ticker` and reads `current_date`/`trade_date`;
- computes `start_date = trade_date − lookback_days` (default 7) and `end_date = trade_date`;
- **pre-fetches three text blocks directly** (not via the crew's tools): `news_sentiment_block` (from `get_news._run(...)`), `stocktwits_block` (from `fetch_stocktwits_messages(...)`), and `reddit_block` (from `fetch_reddit_posts(...)`). These feed the sentiment task, which has no bound tools.

The crew's other tasks bind tools directly in `AnalystCrew`: the market task binds
`[get_stock_data, get_indicators]`, the news task binds `[get_news, get_global_news]`,
and the fundamentals task binds the four fundamentals tools. The sentiment task binds
no tools.

Runtime configuration lives in `src/trading_agents/config/settings.py`. `AppSettings`
is a `pydantic_settings.BaseSettings` with `env_prefix="TRADING_AGENTS_"` and nested
delimiter `__`, so a field like `analyst_stage.lookback_days` is overridden by the
environment variable `TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS`. `get_settings()`
is decorated with `functools.lru_cache`, so it returns a singleton; after changing
environment variables in-process you must call `get_settings.cache_clear()` for the
change to take effect. Relevant existing fields: `analyst_stage.lookback_days` (7),
`sentiment.reddit_recency_window_seconds` (604800), `portfolio_stage.max_holding_days`
(5), `portfolio_stage.max_lessons` (30), and the benchmark map (US tickers map to
`SPY`).

The portfolio stage's realized-return math lives in
`src/trading_agents/crews/portfolio_crew/lesson_store.py`. The key functions are pure
and operate on a *close-price series* — a list of `(date, close)` tuples sorted
ascending: `compute_realized_metrics(instrument, benchmark, trade_date, max_holding_days)`
returns `(raw_return, alpha_return, holding_days)`. `default_fetch_series(symbol, trade_date)`
is the live yfinance-backed fetcher, and `run_portfolio_stage(inputs, *, fetch_series=...)`
accepts a substitute fetcher — this is the seam the evaluation uses to feed prices
from the dataset.

Definitions used in this plan:

- *Backtest window*: 2024-01-01 through 2024-03-29 (inclusive), the period over which decisions are made and CR is measured.
- *Buffer*: 2023-12-01 through 2023-12-31, recorded so the configurable look-back windows (`lookback_days`, the Reddit recency window) have data before the first trading day. Prices additionally extend ~14 days past the window end so holding-period returns can be computed for late decisions.
- *Transaction day* / *trading day*: a date on which the exchange is open, identified by the presence of a benchmark (SPY) close price in the dataset.
- *Prepared dataset*: a committed DuckDB file holding the recorded text output of every analyst tool for every (ticker, trading day), plus a daily close-price table.
- *Evaluation mode*: a runtime mode (`settings.evaluation.enabled == True`) in which the analyst tools and the pre-fetched sentiment blocks read from the prepared dataset instead of calling live APIs.
- *Cumulative return (CR)*: per the README, `total_trading_profit / V_start × 100%`, where `V_start = max(close_at_first_Buy, close_at_first_Overweight / weight_over)`, or `1` if neither a Buy nor an Overweight decision was made.

### Data availability (the crux)

Audited against the backtest window, queried from 2026:

- Prices and indicators are fully available historically (`yf.download(start, end)`), so the builder can record them by calling the existing `get_stock_data_text` / `get_indicators_text`.
- Financial statements return real filings but yfinance keeps only ~4 recent periods, so some 2023-2024 quarters may have rolled off; `get_fundamentals` (`.info`) is a current snapshot, not point-in-time. The builder records best-effort current values; SEC EDGAR is noted as a future point-in-time upgrade. This is acceptable because the profile and statement fields are slow-moving context, and the dominant CR drivers are price action and the daily decisions.
- News (`get_news`, `get_global_news`) and social posts (Reddit, StockTwits) are **not** historically queryable through the existing tools, so the builder sources them from **Exa** with published-date filters.
- Reddit is a required source for this evaluation, not an optional enhancement. A live
  Exa probe on 2026-06-12 found no Reddit results for the earliest buffer window
  (2023-12-01..2023-12-10) and sampled 2024-Q1 windows. The next implementation must
  verify source availability before writing data and stop early if Reddit or another
  required source is missing.


## Plan of Work

The work is additive: new code lives in a new package `src/trading_agents/evaluation/`,
and the only edits to existing files are a new settings block, a small tool-injection
seam in the analyst crew, two new script entry points in `pyproject.toml`, a pointer
edit in the end-to-end-flow plan (`plans/08_end_to_end_flow.md`), and an `EXA_API_KEY`
note in the README. Live behavior is unchanged unless `settings.evaluation.enabled` is
true.

First, extend settings. In `src/trading_agents/config/settings.py`, define
`EvaluationSettings(BaseModel)` with fields `enabled: bool = False`,
`dataset_path: str = "data/eval_dataset.duckdb"`,
`tickers: tuple[str, ...] = ("AAPL", "GOOGL", "AMZN")`, `benchmark: str = "SPY"`,
`start_date: str = "2024-01-01"`, `end_date: str = "2024-03-29"`,
`buffer_start_date: str = "2023-12-01"`, `price_tail_days: int = 14`,
`weight_over: float = 0.5`, and `weight_under: float = 0.5`. Add
`evaluation: EvaluationSettings = EvaluationSettings()` to `AppSettings`. The
`weight_over`/`weight_under` defaults are the README backtest constants.

Second, add an Exa source module `src/trading_agents/evaluation/exa_sources.py`. It
constructs an Exa client from `EXA_API_KEY` and exposes functions that return text
blocks shaped like the existing tools' output, so downstream prompts are byte-for-byte
familiar: `fetch_news_via_exa(query, start_date, end_date, limit)` (Exa `news` search
with `start_published_date`/`end_published_date`, rendered in the
`_format_news_block` style imported from `trading_agents.tools.news`),
`fetch_global_news_via_exa(curr_date, look_back_days, limit)`,
`fetch_reddit_via_exa(ticker, start_date, end_date, ...)` and
`fetch_stocktwits_via_exa(ticker, start_date, end_date, ...)` (domain-restricted Exa
searches using `include_domains=["reddit.com"]` / `["stocktwits.com"]`, rendered to
match the sentiment block format, with a graceful "No data available …" fallback).
Only the builder imports this module.

Third, add the dataset layer `src/trading_agents/evaluation/dataset.py`. Define
`EvalDataset` wrapping a DuckDB connection with two tables created on demand:
`tool_outputs(tool_name TEXT, ticker TEXT, as_of_date TEXT, payload TEXT, PRIMARY KEY (tool_name, ticker, as_of_date))`
and `prices(symbol TEXT, date TEXT, close DOUBLE, PRIMARY KEY (symbol, date))`. Provide
read methods `tool_output(tool_name, ticker, as_of_date) -> str` (raising a clear error
if a needed row is missing, so eval runs fail loudly rather than silently feeding empty
data), `close_series(symbol) -> list[tuple[str, float]]` (ascending), and
`transaction_days() -> list[str]` (benchmark dates within `[start_date, end_date]`).
Provide idempotent upsert helpers `put_tool_output(...)` and `put_prices(symbol, rows)`
used by the builder (use `INSERT OR REPLACE`).

Fourth, add the builder `src/trading_agents/evaluation/build_dataset.py` with a
`build-eval-dataset` console entry point, but split it into two explicit phases. Phase 1
is source availability verification and always runs before any DuckDB writes. It checks
the earliest risky source window first: `buffer_start_date` through nine calendar days
later (currently 2023-12-01 through 2023-12-10). For each ticker, call the Exa helpers
for ticker news, Reddit, and StockTwits with a tiny limit such as 3, and call global
news once for the same window. Treat fallback strings such as
`No data available for Reddit posts for AAPL.` or `No news found ...` as unavailable.
Because Reddit is required, missing Reddit must fail the command. On failure, print a
compact source-by-source report and exit nonzero before opening or creating the DuckDB
dataset.

Phase 2 runs only after the availability gate passes. It downloads daily closes for
each ticker and the benchmark over `buffer_start_date … end_date + price_tail_days` and
fills `prices`; derives the trading-day list from the benchmark price index within the
window; and for each ticker × trading day, records into `tool_outputs` the text from
`get_stock_data_text`/`get_indicators_text` (called with the same
`start = trade_date − lookback_days`, `end = trade_date` the eval flow uses), the Exa
news and global-news blocks, the Exa Reddit and StockTwits blocks, and best-effort
fundamentals/statement text. Use `EvalDataset.put_prices()` and `put_tool_output()` so
the build is idempotent. Support `--tickers`, `--limit-days`, `--verify-only`, and
`--scan-periods`. `--verify-only` runs Phase 1 and exits without creating the dataset.
`--scan-periods` checks candidate 61-trading-day windows, such as later 2024 quarters
and 2025-Q1, and reports whether every required source is available; it must not change
`EvaluationSettings.start_date` or `end_date`.

Fifth, add evaluation tools and the analyst-crew seam. In
`src/trading_agents/evaluation/eval_tools.py`, define dataset-backed `BaseTool`
subclasses (one per analyst tool name) constructed with `(EvalDataset, ticker, as_of_date)`
whose `_run(...)` ignores the language model's arguments and returns
`dataset.tool_output(name, ticker, as_of_date)`. Then make `AnalystCrew` accept injected
tools: refactor `src/trading_agents/crews/analyst_crew/analyst_crew.py` so the
per-task tool lists come from a small provider (default = the current live tool
instances), and have `run_analyst_stage` build dataset-backed tools when
`get_settings().evaluation.enabled` is true. In the same file, make
`prepare_analyst_inputs` read `news_sentiment_block`, `stocktwits_block`, and
`reddit_block` from the dataset when evaluation mode is enabled (keyed by ticker and
trade date), instead of calling the live functions. Keep the change minimal and
preserve the existing behavior when evaluation mode is off.

Sixth, add the simulator `src/trading_agents/evaluation/backtest.py` as pure functions.
`simulate_position(decisions, closes, weight_over, weight_under)` walks a chronological
list of `(date, rating)` decisions with the matching close prices and applies the
README rules exactly: position in `[0, 1]`; transaction price is the trade-day close;
`Buy` raises to 1 if below 1; `Overweight` raises to `weight_over` if below it; `Hold`
holds; `Underweight` reduces to `weight_under` if above it; `Sell` reduces to 0 if above
0; `Underweight` and `Sell` are ignored at zero position; on raises the cost basis is
updated, on reductions realized profit accrues; a forced `Sell` is appended on the last
trading day. `cumulative_return(...)` computes CR with `V_start` as defined above
(`V_start = 1` when neither Buy nor Overweight occurred). These functions take prices and
decisions as arguments and perform no I/O, so they are unit-testable without any network.

Seventh, add the orchestrator `src/trading_agents/evaluation/run_eval.py` with a
`run-eval` console entry point. It sets `TRADING_AGENTS_EVALUATION__ENABLED=true` and
calls `get_settings.cache_clear()` before importing the stage helpers (or imports them
lazily), opens the dataset, and uses an isolated lessons directory (for example a
`LessonStore(base_dir="output/eval/lessons")`) and a dataset-backed `fetch_series`
reading the `prices` table. It iterates the trading days **chronologically** (the
portfolio lesson store accumulates lessons across days), and for each day runs each
ticker through the five stages — either by kicking off `TradingAgentsFlow` per
(ticker, day) or by calling the stage helpers directly — capturing the
`PortfolioDecision.rating`. It feeds the per-(ticker, date) decisions into the simulator
and writes a report (markdown and CSV) under `output/eval/`, including a header noting
the run is language-model-expensive. Support `--tickers` and `--limit-days` for cheap
smoke runs.

Eighth, register the entry points in `pyproject.toml` under `[project.scripts]`:
`build-eval-dataset = "trading_agents.evaluation.build_dataset:main"` and
`run-eval = "trading_agents.evaluation.run_eval:main"`. Add `EXA_API_KEY` to the
README's Installation/Customizing notes and to the project `.env` expectations.

Ninth, push back the end-to-end-flow plan (`plans/08_end_to_end_flow.md`, formerly
`plans/07_end_to_end_flow_and_evaluation.md`): remove its open evaluation checklist
item and the "Sixth, add an evaluation runner …" paragraph, replace them with a
one-line pointer to this plan, and add a Revision Note recording the split and the
renumber. (Done in the same change set as this plan.) The existing
`tests/eval_cases/trading_agent_eval_cases.yaml` is a separate qualitative regression
screen, orthogonal to the CR backtest, and is left for a possible future plan.


## Concrete Steps

Run all commands from `/app/trading_agents`.

1. Confirm the current settings load and that the analyst stage helpers import:

       uv run python -c "from trading_agents.config import get_settings; print(type(get_settings()).__name__)"
       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage, prepare_analyst_inputs; print('analyst ok')"

   Expected: `AppSettings` and `analyst ok`.

2. After adding `EvaluationSettings`, verify it is reachable:

       uv run python -c "from trading_agents.config import get_settings; print(get_settings().evaluation.tickers, get_settings().evaluation.enabled)"

   Expected:

       ('AAPL', 'GOOGL', 'AMZN') False

3. Write the unit tests and run them (they must fail before the simulator/dataset code
   exists and pass after):

       uv run pytest tests/test_eval_backtest.py tests/test_eval_dataset.py

   Expected after implementation: all tests pass. The backtest tests assert the README
   rules and the CR formula on hand-built decision sequences; the dataset tests round-trip
   rows through a temporary DuckDB file and confirm a dataset-backed eval tool returns the
   recorded payload.

4. Before building any dataset, verify historical source availability (needs
   `EXA_API_KEY` and network):

       uv run build-eval-dataset --verify-only

   Expected if every required source is available: a source-by-source report showing
   `available` for ticker news, global news, Reddit, and StockTwits for the earliest
   risky buffer window, followed by a zero exit code and no DuckDB file creation.

   Expected if Reddit remains unavailable: a nonzero exit with a report naming the
   missing Reddit rows, for example `AAPL reddit unavailable for 2023-12-01..2023-12-10`.
   In this case, stop and do not run the dataset build. Use the scan command below to
   search for a viable replacement period:

       uv run build-eval-dataset --scan-periods

   Expected scan behavior: print candidate windows and whether all required sources are
   available. Do not update settings or write the dataset automatically.

5. Build a small dataset slice only after `--verify-only` passes:

       uv run build-eval-dataset --tickers AAPL --limit-days 3

   Expected: a summary line reporting that `data/eval_dataset.duckdb` now holds
   `tool_outputs` rows for the ten tool names × AAPL × 3 days, plus `prices` rows for AAPL
   and SPY. Inspect with:

       uv run python -c "from trading_agents.evaluation.dataset import EvalDataset; d=EvalDataset(); print(len(d.transaction_days()), 'days'); print(d.tool_output('get_stock_data','AAPL',d.transaction_days()[0])[:120])"

6. Run an offline evaluation smoke run over the slice (needs `OPENAI_API_KEY`; no other
   network):

       uv run run-eval --tickers AAPL --limit-days 3

   Expected: a console summary and an `output/eval/` report listing each day's rating for
   AAPL and a CR value. No live calls should be made to yfinance/Reddit/StockTwits — the
   analyst tools and the pre-fetched sentiment blocks read from the dataset.

7. Build the full dataset and run the full evaluation (language-model-expensive):

       uv run build-eval-dataset
       uv run run-eval

   Expected: a report giving CR for AAPL, GOOGL, and AMZN over the window. Record the
   numbers in `Outcomes & Retrospective` and compare them qualitatively to Table 1.

8. Commit the dataset and code:

       git add data/eval_dataset.duckdb src/trading_agents/evaluation tests/test_eval_*.py
       git commit


## Validation and Acceptance

Acceptance is behavioral:

- `uv run pytest tests/test_eval_backtest.py tests/test_eval_dataset.py` passes; the new
  tests fail on a clean checkout before this plan and pass after.
- `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py`
  passes after the builder is added. The builder tests must mock Exa/yfinance and assert
  that verification failure prevents dataset writes.
- `uv run build-eval-dataset --verify-only` performs the required-source check before
  any DuckDB writes. If Reddit or another required source is unavailable, the command
  exits nonzero with a clear report and does not create or update
  `data/eval_dataset.duckdb`.
- `uv run build-eval-dataset --tickers AAPL --limit-days 3` produces a DuckDB file with
  the expected `tool_outputs` and `prices` rows only after source verification passes,
  and is idempotent (running it twice does not duplicate rows).
- `uv run run-eval --tickers AAPL --limit-days 3` produces a per-day rating list and a CR
  value while reading only from the dataset for analyst data (verifiable by running with
  network disabled, or by asserting in a test that the dataset-backed tools were used).
- The full `uv run run-eval` reports a CR per stock over 2024-Q1.

A concrete simulator acceptance example to encode as a test: with `weight_over = 0.5`,
a single `Buy` on day 1 at close 100, holds through, and the forced `Sell` on the last
day at close 110, yields realized profit 10 and `V_start = 100`, so `CR = +10.0%`. A
Hold-only sequence yields `V_start = 1` and `CR` equal to the realized profit (0 if no
position is ever taken) as a percentage.


## Idempotence and Recovery

The availability gate runs before any DuckDB connection is opened for writing. If
`EXA_API_KEY` is missing, or if ticker news, global news, Reddit, or StockTwits is
unavailable for the required probe window, the builder fails with a clear report and
leaves the dataset untouched. `--verify-only` and `--scan-periods` are read-only with
respect to `data/eval_dataset.duckdb`.

After the gate passes, the dataset build uses `INSERT OR REPLACE`, so it can be run
repeatedly and partially (via `--tickers`/`--limit-days`) without duplicating rows;
rerunning refreshes existing rows. The evaluation run writes only under `output/eval/`
and uses an isolated lessons directory there, so it never disturbs ordinary
`output/<ticker>_<date>/` run artifacts; delete `output/eval/` to start a clean
evaluation. If the build is interrupted after the gate passes, rerun it — completed
(ticker, day) rows are simply overwritten. If a needed `tool_outputs` row is missing at
evaluation time, `EvalDataset.tool_output` raises a clear error naming the
tool/ticker/date so the gap is obvious rather than masked by empty input.


## Artifacts and Notes

Representative builder summary (illustrative):

    Source availability check — 2023-12-01..2023-12-10
    AAPL  news available | reddit unavailable | stocktwits available
    GOOGL news available | reddit unavailable | stocktwits available
    AMZN  news available | reddit unavailable | stocktwits available
    global_news available
    ERROR: required source unavailable; dataset was not written

Representative successful builder summary (illustrative):

    Built data/eval_dataset.duckdb
    tickers: AAPL, GOOGL, AMZN | benchmark: SPY
    trading days in window: 61 (2024-01-02 .. 2024-03-28)
    tool_outputs rows: 1830 | prices rows: 352
    note: 2024-03-29 is Good Friday (market closed); last trading day is 2024-03-28

Representative evaluation report (illustrative):

    TradingAgents evaluation — 2024-01-01..2024-03-29 (61 trading days)
    weight_over=0.5 weight_under=0.5 | language-model calls: 183 flow runs
    AAPL   first Buy 2024-01-09 @ 185.14 | V_start=185.14 | CR = +4.2%
    GOOGL  first Overweight 2024-01-11 @ 142.30 | V_start=284.60 | CR = +9.1%
    AMZN   first Buy 2024-01-05 @ 145.24 | V_start=145.24 | CR = +12.7%

Known limitations to keep in mind: fundamentals are best-effort current snapshots, not
point-in-time; the trading-day count is derived from the actual price calendar and
equals the README's 61 (2024-01-02 .. 2024-03-28, with 2024-03-29 a closed holiday);
Reddit is currently the likely historical-source blocker; and the full run is
language-model-expensive (3 × 61 = 183 flow runs), which is why `--limit-days` exists.


## Interfaces and Dependencies

Use these libraries and modules: `duckdb` for the dataset (already a dependency),
`exa-py` for historical news/social (already a dependency; needs `EXA_API_KEY`),
`yfinance` for prices/indicators/fundamentals (already used by the tools), and the
existing crew stage helpers in `src/trading_agents/main.py` for orchestration.

At the end of this plan these names must exist:

In `src/trading_agents/config/settings.py`:

    class EvaluationSettings(BaseModel):
        enabled: bool
        dataset_path: str
        tickers: tuple[str, ...]
        benchmark: str
        start_date: str
        end_date: str
        buffer_start_date: str
        price_tail_days: int
        weight_over: float
        weight_under: float
    # AppSettings gains: evaluation: EvaluationSettings

In `src/trading_agents/evaluation/dataset.py`:

    class EvalDataset:
        def __init__(self, path: str | None = None) -> None: ...
        def tool_output(self, tool_name: str, ticker: str, as_of_date: str) -> str: ...
        def close_series(self, symbol: str) -> list[tuple[str, float]]: ...
        def transaction_days(self) -> list[str]: ...
        def put_tool_output(self, tool_name: str, ticker: str, as_of_date: str, payload: str) -> None: ...
        def put_prices(self, symbol: str, rows: list[tuple[str, float]]) -> None: ...

In `src/trading_agents/evaluation/backtest.py`:

    def simulate_position(decisions: list[tuple[str, str]], closes: dict[str, float], weight_over: float, weight_under: float) -> "BacktestResult": ...
    def cumulative_return(result: "BacktestResult", weight_over: float) -> float: ...

In `src/trading_agents/evaluation/exa_sources.py`:

    def fetch_news_via_exa(query: str, start_date: str, end_date: str, limit: int) -> str: ...
    def fetch_global_news_via_exa(curr_date: str, look_back_days: int, limit: int) -> str: ...
    def fetch_reddit_via_exa(ticker: str, start_date: str, end_date: str, limit: int) -> str: ...
    def fetch_stocktwits_via_exa(ticker: str, start_date: str, end_date: str, limit: int) -> str: ...

In `src/trading_agents/evaluation/build_dataset.py` and `run_eval.py`, a `main()` each,
registered as `build-eval-dataset` and `run-eval` in `pyproject.toml`.

In `src/trading_agents/evaluation/build_dataset.py`, define builder helpers with these
observable behaviors:

    def main(argv: list[str] | None = None) -> int: ...
    def verify_source_availability(tickers: list[str]) -> "AvailabilityReport": ...
    def build_dataset(tickers: list[str], limit_days: int | None = None) -> "BuildSummary": ...

`main()` parses `--verify-only`, `--tickers`, `--limit-days`, and `--scan-periods`.
`verify_source_availability()` must return enough structured data for tests to assert
which source failed, and `main()` must return a nonzero exit code when any required
source is unavailable. `build_dataset()` must be called only after verification passes.

The analyst crew (`src/trading_agents/crews/analyst_crew/analyst_crew.py`) must keep its
existing public functions `run_analyst_stage`, `prepare_analyst_inputs`, and
`extract_analyst_reports` working unchanged when evaluation mode is off, while gaining an
internal seam that swaps in dataset-backed tools and dataset-sourced sentiment blocks when
`get_settings().evaluation.enabled` is true.

Revision Note: 2026-06-11 Initial ExecPlan drafted after auditing the ten analyst data
tools against the 2024-Q1 backtest window, confirming that news and social sources are not
historically queryable through the existing tools, confirming Exa (already a dependency)
supports published-date filtering, and confirming with the user the choice of Exa for
news/social and a committed DuckDB dataset. This plan was split out of the
end-to-end-flow ExecPlan, whose evaluation scope is correspondingly pushed back.

Revision Note: 2026-06-11 Renumbered this evaluation ExecPlan from 08 to 07 (and the
end-to-end-flow ExecPlan from 07 to 08, renamed `plans/08_end_to_end_flow.md`) at the
user's request, so the next-to-implement work carries the active plan number. All
cross-references between the two files were updated accordingly.

Revision Note: 2026-06-12 Split the pending dataset-builder task into a source
availability gate, the actual DuckDB build phase, and a candidate-period scan fallback.
This revision was made after the user raised historical availability as a major concern
and confirmed that Reddit is required. A live Exa probe found early-window news,
global-news, and StockTwits results but no Reddit results, so the plan now requires
`build-eval-dataset --verify-only` to fail before DuckDB writes when any required source
is unavailable.
