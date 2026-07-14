# Build the TradingAgents Plan B Evaluation: a 2026-Q1 Cumulative-Return Backtest

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.


## Purpose / Big Picture

After this change, a user can run the same TradingAgents cumulative-return evaluation described in `plans/07_evaluation_backtest.md`, but over a practical Plan B period: 2026-Q1. Plan 07 remains the canonical README and paper reproduction for 2024-Q1. This Plan B exists because the historical Reddit source needed for 2024-Q1 was not available through the tested providers, while the completed Reddit coverage scanner ranked 2026-Q1 as the best available alternate quarter.

The user-visible behavior should be the same as Plan 07 except for the dates and dataset artifact. From the project root, a user can build an isolated Plan B prepared dataset and run the backtest:

    uv run build-plan-b-eval-dataset

    TRADING_AGENTS_EVALUATION__START_DATE=2026-01-01 \
    TRADING_AGENTS_EVALUATION__END_DATE=2026-03-31 \
    TRADING_AGENTS_EVALUATION__BUFFER_START_DATE=2025-12-01 \
    TRADING_AGENTS_EVALUATION__DATASET_PATH=data/eval_dataset_2026q1.duckdb \
    uv run run-eval

and sees a report such as:

    TradingAgents Plan B evaluation — 2026-01-01..2026-03-31 (61 trading days)
    AAPL   CR = +3.8%
    GOOGL  CR = +6.4%
    AMZN   CR = +8.9%

The concrete result values above are illustrative. The final implementation must record the actual cumulative return, abbreviated CR, for AAPL, GOOGL, and AMZN in this plan's `Outcomes & Retrospective`.


## Progress

- [x] (2026-06-16) Completed the Plan B Reddit coverage scanner and recorded its recommendation in `plans/07_evaluation_backtest.md`: 2026-Q1 ranked first with `posts=176`, `>=1 coverage=82.0%`, `>=3 coverage=71.6%`, `min ticker coverage=50.8%`, and `pairs=6/9`.
- [x] (2026-06-16) Verified the 2026-Q1 trading calendar with yfinance: SPY, AAPL, GOOGL, and AMZN each have 61 rows from 2026-01-02 through 2026-03-31 for the inclusive Plan B window `2026-01-01..2026-03-31`.
- [x] (2026-06-16) Added the `build-plan-b-eval-dataset` entry point skeleton and verified it uses Plan B dates and dataset path without taking over the reserved Plan 07 `build-eval-dataset` command; `--verify-only` prints resolved settings and skips DuckDB writes.
- [x] (2026-06-17 00:00Z) Implemented the shared price-table and trading-day calendar build for Plan B: write close prices for selected tickers and the default benchmark ticker, SPY, into `data/eval_dataset_2026q1.duckdb` before recording per-tool payloads. A live smoke run for `--tickers AAPL --limit-days 3` wrote 92 AAPL rows and 92 SPY rows and derived transaction days `2026-01-02..2026-01-06`.
- [x] (2026-06-17 06:37Z) Implemented Plan B dataset building for `get_stock_data` through the shared Plan 07 builder path: record the market-data text block for AAPL, GOOGL, AMZN, and SPY on each trading day using the same lookback window the analyst stage will request; SPY history is required by the portfolio manager's self-reflection and benchmark-relative realized-return calculations.
- [x] (2026-06-17) Implemented and populated Plan B dataset building for `get_indicators` through the shared Plan 07 builder path: records all allowed indicators from `src/trading_agents/tools/market_data.py` for each configured ticker and trading day using the analyst-stage lookback window. Wrote 183 persistent `get_indicators` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero SPY indicator rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison matched for `AMZN` on `2026-02-27` with 12 indicators.
- [x] (2026-06-17 13:03Z) Implemented and populated Plan B dataset building for `get_news` through the shared Plan 07 builder path: records ticker-news text through the Exa historical source layer with the same markdown/no-news/error contract as the live Yahoo-backed tool. The builder uses a doubled news limit (`settings.news.ticker_limit * 2`, currently 40) for buffer coverage and writes ticker rows only. Wrote 183 persistent `get_news` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero error payloads and zero no-news fallback rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`.
- [x] (2026-06-17) Implemented and populated Plan B dataset building for `get_global_news` through the shared Plan 07 builder path: records one Exa historical global-market-news payload per trading day, stores it under each evaluated ticker key for existing dataset-backed tool replay, and uses a doubled global-news limit (`settings.news.global_limit * 2`, currently 20). Wrote 183 persistent `get_global_news` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Source warning: Exa returned HTTP 402 credit-limit errors after 52 successful days, so 27 rows across 9 dates currently contain explicit `Error fetching global news ... exceeded your credits limit` payloads; zero rows use the no-news fallback. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2026-01-16`; the evaluation-backed `get_global_news` tool matched the DuckDB payload exactly and returned the shared global payload for all ticker keys on that date.
- [x] (2026-06-18 07:22Z) Implemented and populated Plan B dataset building for `fetch_reddit_posts`: added a raw `reddit_posts` DuckDB table, collected Reddit RSS with OR-joined aliases and a 10-second inter-request delay, stored all fetched raw posts, and generated capped replay payloads for each ticker/trading day. Wrote 900 raw Reddit post rows to `data/eval_dataset_2026q1.duckdb` (AAPL 300, GOOGL 300, AMZN 300) and 183 persistent `fetch_reddit_posts` rows in `tool_outputs` (3 tickers times 61 transaction days). Focused validation passed with `uv run pytest tests/test_eval_dataset.py tests/test_eval_build_dataset.py tests/test_eval_reddit_coverage.py`; `ruff` was unavailable in the environment. Reddit returned multiple bounded HTTP 429 retries during population, but the run completed.
- [x] (2026-07-14) Implemented and populated Plan B dataset building for
  `fetch_stocktwits_messages`: reads the Stage 1 raw StockTwits JSON coverage files
  under `data/raw-backtest/stocktwits`, renders 7-day lookback payloads in the same
  summary and message-line format as the live helper, and writes replay rows without
  calling the StockTwits API. Wrote 183 persistent `fetch_stocktwits_messages` rows
  to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero
  no-data rows.
- [x] (2026-07-14 12:35Z) Repaired the AAPL `get_news` payloads for 2026-01-27
  and 2026-01-30 without calling Exa. Removed one complete contaminated
  MarketScreener article block from each row because its generated summary embedded
  market data dated 2026-06-12 and 2026-06-08, respectively. Both repaired payloads
  retain 38 articles and contain no valid ISO date later than their trade date;
  `tests/test_eval_dataset.py` passed with 8 tests.
- [x] (2026-07-14) Repaired the AMZN `get_news` payloads for 2026-02-09,
  2026-03-11, 2026-03-16, and 2026-03-17 without calling Exa. Removed one complete
  contaminated MarketScreener article block from each row because the generated
  summaries embedded market data dated 2026-06-15, 2026-04-17, or 2026-03-18.
  The repaired payloads contain no valid ISO date later than their trade date, all
  183 `get_news` rows remain present, and `tests/test_eval_dataset.py` passed with
  8 tests.
- [x] Implement Plan B dataset building for `get_fundamentals`: record best-effort fundamentals text for each ticker and trading day.
- [x] (2026-06-18 14:16Z) Implemented and populated Plan B dataset building for `get_balance_sheet` through the shared Plan 07 builder path: records the yfinance latest balance-sheet statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_balance_sheet` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2026-01-21`; the evaluation-backed `get_balance_sheet` tool matched the live tool exactly and AAPL had one distinct payload across all 61 replay dates.
- [x] (2026-06-18 14:24Z) Implemented and populated Plan B dataset building for `get_cashflow` through the shared Plan 07 builder path: records the yfinance latest cash flow statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_cashflow` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2026-01-09`; the evaluation-backed `get_cashflow` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [x] (2026-06-18 14:30Z) Implemented and populated Plan B dataset building for `get_income_statement` through the shared Plan 07 builder path: records the yfinance latest income statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_income_statement` rows to `data/eval_dataset_2026q1.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used GOOGL on `2026-03-18`; the evaluation-backed `get_income_statement` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [ ] (pending) Run a Plan B smoke evaluation, for example AAPL over three trading days, and record the observed command output.
- [ ] (pending) Run the full Plan B evaluation for AAPL, GOOGL, and AMZN over the 61 trading days and record CR per stock in `Outcomes & Retrospective`.

Use timestamps, for example `(2026-06-16 09:00Z)`, when checking items off so a future contributor can gauge the rate of progress.


## Surprises & Discoveries

- Observation: The original 2024-Q1 evaluation period remains the canonical target, but Reddit was the historical-source blocker.
  Evidence: `plans/07_evaluation_backtest.md` records Exa probes that found ticker news, global news, and StockTwits for early 2023-12 buffer windows, while Reddit searches for AAPL, GOOGL, and AMZN returned no historical results.

- Observation: Reddit RSS is useful for recent coverage diagnostics, but it is recency-limited and does not provide arbitrary historical date-range access.
  Evidence: `plans/07_evaluation_backtest.md` records that Reddit RSS returns the 100 newest posts per query with `t=year&limit=100`, reaching back only to approximately August 2025 during the scan. This makes recent quarters much easier to evaluate than 2024-Q1.

- Observation: The Reddit HTTP 429 issue during Plan B scanning was caused by request volume against the unauthenticated RSS endpoint from this cloud/datacenter IP, not by a total IP block.
  Evidence: A single Reddit RSS request returned HTTP 200, but the first scanner design made `3 tickers × 3 subreddits × 3 query aliases = 27` sequential requests and repeatedly hit HTTP 429. `plans/07b_reddit_coverage_scanner.md` records the fix: OR-join aliases into one query per `(ticker, subreddit)`, reducing volume to 9 requests, and honor `Retry-After` before falling back to bounded fixed backoff. The successful scanner run used `--delay 8`; use at least 10 seconds between Reddit RSS requests in dataset ingestion to add a 2-second safety buffer.

- Observation: The Plan B Reddit coverage scanner recommended 2026-Q1.
  Evidence: `uv run python -m trading_agents.evaluation.reddit_coverage --delay 8` printed `1. 2026-Q1: posts=176, >=1 coverage=82.0%, >=3 coverage=71.6%, min ticker coverage=50.8%, pairs=6/9`, followed by `2025-Q4` and `2025-Q3` with substantially weaker coverage.

- Observation: 2026-Q1 has the same transaction-day count as the README's 2024-Q1 window.
  Evidence: On 2026-06-16, `yf.download` for SPY, AAPL, GOOGL, and AMZN over `start='2026-01-01', end='2026-04-01'` returned 61 rows each, first row `2026-01-02` and last row `2026-03-31`.

- Observation (2026-06-17): The Exa Python SDK call path used by `exa_sources.py`
  does not expose a timeout parameter and internally calls `requests.post()` without
  a timeout, so one slow response can stall a dataset build indefinitely.
  Evidence: an interrupted `get_news` ingestion was blocked in
  `exa_py/api.py:requests.post(...).getresponse()`. The fix wraps the SDK's internal
  requests functions with a 20-second default timeout and records per-row
  `Error fetching news for ...` payloads if a historical news fetch fails.
- Observation (2026-06-17): The first timeout wrapper still allowed indefinite waits
  when the Exa SDK passed `timeout=None`, because `dict.setdefault()` did not override
  the explicit `None`.
  Evidence: an interrupted `get_global_news` ingestion was blocked inside
  `requests.post(... timeout=None ...)`; the wrapper now replaces `None` with the
  20-second default, and `tests/test_eval_exa_sources.py::test_exa_timeout_patch_overrides_explicit_none`
  covers the regression.
- Observation (2026-06-17): The Plan B `get_global_news` population is degraded by
  Exa quota exhaustion, not by missing code or missing DuckDB rows.
  Evidence: read-only DuckDB queries found 183 `get_global_news` rows in
  `data/eval_dataset_2026q1.duckdb`, but 27 rows across 9 dates contain HTTP 402
  `You have exceeded your credits limit` payloads from Exa. The failed Plan B
  dates to retry in July after monthly Exa credits reset are: `2026-02-18`,
  `2026-02-19`, `2026-03-11`, `2026-03-12`, `2026-03-16`, `2026-03-17`,
  `2026-03-20`, `2026-03-24`, and `2026-03-26`.
- Observation (2026-06-18): Plan B Reddit population still hit Reddit's
  unauthenticated RSS rate limit even with the fixed 9-request path and a 10-second
  inter-request delay, but bounded retries were sufficient for this run.
  Evidence: the population run printed repeated HTTP 429 retry warnings for several
  ticker/subreddit feeds, then completed with `posts_written: 900`,
  `payloads_written: 183`, `transaction_days: 61`, and
  `request_delay_seconds: 10.0`.
- Observation (2026-07-14): Stage 1 StockTwits raw-file coverage is sufficient for
  Plan B.
  Evidence: the user completed the Stage 1 scanner with `reached_cutoff=True` for
  AAPL, GOOGL, and AMZN. The oldest cutoff files were `AAPL-1739.json`,
  `GOOGL-0695.json`, and `AMZN-1214.json`, all reaching 2025-12-17 before the
  Plan B buffer cutoff of 2025-12-18.
- Observation (2026-07-14): The Plan B StockTwits replay payloads match the live
  helper's text contract when both are fed the same raw messages.
  Evidence: a random validation picked GOOGL on `2026-02-12`; the dataset payload
  exactly matched `fetch_stocktwits_messages("GOOGL", limit=30, timeout=10.0)` with
  its HTTP JSON fetch replaced by the same selected raw messages from disk. The
  shared summary was `Bullish: 11 (37%) · Bearish: 3 (10%) · Unlabeled: 16 · Total:
  30 most-recent messages`.
- Observation (2026-07-14): Exa-generated summaries can embed market data from
  after the requested historical window even when the surrounding result was
  selected for an earlier date.
  Evidence: six AAPL and AMZN `get_news` payloads contained MarketScreener summaries
  with market data later than their trade dates. Targeted offline repairs removed
  the complete offending article blocks and left all 183 `get_news` rows present.

Add new observations here as they arise, with a short evidence snippet. Test output is ideal.


## Decision Log

- Decision: Use 2026-Q1 as the Plan B backtest period.
  Rationale: The Plan B Reddit coverage scanner ranked 2026-Q1 first by ticker-day Reddit coverage, stricter three-post coverage, minimum per-ticker coverage, ticker/subreddit pair breadth, and total posts. This makes it the most practical alternate quarter for a full evaluation with Reddit included.
  Date/Author: 2026-06-16 / Codex

- Decision: Keep Plan B separate from the canonical Plan 07 backtest.
  Rationale: Plan 07 reproduces the README and paper period, 2024-Q1. Plan B is a data-availability fallback and should not blur the interpretation of canonical results.
  Date/Author: 2026-06-16 / Codex

- Decision: Store the Plan B dataset in `data/eval_dataset_2026q1.duckdb` instead of `data/eval_dataset.duckdb`.
  Rationale: The canonical Plan 07 dataset path should remain reserved for the README/paper period. An isolated artifact lets users rebuild either dataset without overwriting the other.
  Date/Author: 2026-06-16 / Codex

- Decision: Reuse the Plan 07 evaluation architecture rather than adding a second evaluator.
  Rationale: The only intentional difference is the backtest period. Dataset record/replay, dataset-backed analyst tools, portfolio-stage price replay, and cumulative-return scoring should remain identical so Plan B is comparable in mechanics even though it is not the same historical market period.
  Date/Author: 2026-06-16 / Codex

- Decision: Split Plan B dataset-builder progress by the ten analyst data tools.
  Rationale: The Reddit HTTP 429 investigation showed that each data source can fail
  for a different operational reason: request volume, provider rate limits, blocked
  endpoints, empty historical coverage, parser errors, or stale API assumptions. The
  Plan B dataset should be built and validated one tool at a time so source-specific
  problems are diagnosed and fixed without hiding them inside a single broad "build
  dataset" task.
  Date/Author: 2026-06-16 / Codex

- Decision: Use the same `build_price_table()` implementation for Plan B and the
  canonical Plan 07 evaluation.
  Rationale: The only intended difference between the two evaluations is the period
  and dataset artifact. Prices, benchmark-derived transaction days, yfinance
  normalization, and idempotent DuckDB writes should remain identical.
  Date/Author: 2026-06-17 / Codex

- Decision: Do not apply a source-availability gate to Plan B. Collect Reddit for the
  chosen 2026-Q1 period using the fixed Reddit RSS/request-volume handling.
  Rationale: The user clarified on 2026-06-17 that the Reddit gate applies to Plan 07's
  canonical 2024-Q1 problem, not Plan B. Plan B was selected precisely because the
  fixed scanner can retrieve Reddit posts during 2026-Q1. All Plan B builders,
  including `fetch_reddit_posts`, should be implemented, tested, collected, and
  summarized source by source.
  Date/Author: 2026-06-17 / Codex (user direction)

Record every further decision here, with the reasoning, as the plan evolves.


## Outcomes & Retrospective

Milestone 0 — Plan B builder configuration seam (2026-06-16). Added
`src/trading_agents/evaluation/build_dataset.py` and registered the Plan B-specific
`build-plan-b-eval-dataset` command in `pyproject.toml`. The canonical
`build-eval-dataset` command name remains reserved for the original Plan 07
evaluation. The Plan B command resolves the shared `EvaluationSettings` values that
should remain common, such as tickers, benchmark, weights, and price tail days, while
defaulting its own period and artifact to `2026-01-01..2026-03-31`,
`2025-12-01`, and `data/eval_dataset_2026q1.duckdb`. It supports `--verify-only`
without creating a DuckDB file. Focused tests in
`tests/test_eval_build_dataset.py` cover Plan 07 defaults, Plan B environment
defaults, ticker CLI overrides, and the no-write verify-only behavior. Actual source
availability checks and dataset writes remain pending in the following tool-specific
steps.

No Plan B evaluation run has been completed yet.

Milestone 1 — Shared price table and calendar build (2026-06-17). Added the first
write phase that Plan B shares with Plan 07:

- `src/trading_agents/evaluation/build_dataset.py` now has `build_price_table()`, which
  downloads yfinance close prices for the selected tickers plus SPY from
  `buffer_start_date` through `end_date + price_tail_days`, writes them with
  `EvalDataset.put_prices()`, and derives transaction days from SPY.
- The builder de-duplicates symbols, so SPY is written once even if it appears in the
  ticker subset and as the benchmark.
- Focused validation passed: `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py`
  reported 23 passed.
- Live smoke validation passed: `uv run build-plan-b-eval-dataset --tickers AAPL --limit-days 3`
  wrote `data/eval_dataset_2026q1.duckdb`, recorded 92 close-price rows each for AAPL
  and SPY over `2025-12-01..2026-04-15` with the end date exclusive, and reported
  three transaction days from `2026-01-02` through `2026-01-06`.

Analyst tool-output recording and evaluation runs remain pending. Plan B has no
source-availability gate; Reddit collection should use the fixed 2026-Q1 RSS path and
preserve source statuses in the collected payload summary.

Milestone 2 — Shared `get_stock_data` tool-output builder (2026-06-17). Added the
first analyst tool-output writer that Plan B shares with Plan 07:

- `build_stock_data_outputs()` writes replayable `get_stock_data` payloads for each
  selected ticker plus SPY on each SPY-derived transaction day.
- The builder calls the existing `get_stock_data_text()` renderer with
  `start_date = as_of_date - settings.analyst_stage.lookback_days` and
  `end_date = as_of_date`, matching the analyst stage's default seven-day lookback.
- The Plan B command now reports the stock-data payload count after the price table
  summary and before the remaining pending tool-output builders.
- Focused validation passed: `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py`
  reported 24 passed.

The remaining Plan B dataset-building work starts with `get_indicators`; evaluation
runs are still pending.

Milestone 6 — Shared `fetch_reddit_posts` tool-output builder (2026-06-18). Added
the Reddit builder that Plan B needs for analyst sentiment replay:

- `EvalDataset` now creates and manages a `reddit_posts` table for raw RSS post
  rows, separate from capped prompt-ready `tool_outputs` rows.
- `build_reddit_outputs()` fetches Reddit RSS once per `(ticker, subreddit)` using
  OR-joined ticker aliases from the coverage scanner, writes all returned raw posts,
  and renders a small replay payload for each ticker/trading day.
- The Plan B default Reddit request delay is 10 seconds, with CLI overrides
  `--reddit-delay` and `--reddit-limit-per-sub`; the replay payload limit defaults
  to the existing small sentiment setting, while raw storage is uncapped by that
  replay limit.
- Focused validation passed:
  `uv run pytest tests/test_eval_dataset.py tests/test_eval_build_dataset.py tests/test_eval_reddit_coverage.py`
  reported 32 passed.
- Live population wrote `data/eval_dataset_2026q1.duckdb` with 900 raw Reddit post
  rows and 183 `fetch_reddit_posts` replay rows. A read-only verification query
  confirmed 300 raw rows each for AAPL, AMZN, and GOOGL.

Milestone 7 — Shared `get_balance_sheet` tool-output builder (2026-06-18). Added the
first financial-statement writer that Plan B shares with Plan 07:

- `build_snapshot_tool_outputs()` centralizes the "fetch once per ticker, write every
  transaction day" behavior used by current-snapshot fundamentals and statement tools.
- `build_balance_sheet_outputs()` records `get_balance_sheet` payloads for each
  selected ticker on each SPY-derived transaction day.
- The payload is rendered through the existing `get_statement_text(ticker, "Balance sheet", "balance_sheet")`
  helper, matching the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 53 passed.
- Live population wrote 183 `get_balance_sheet` rows to
  `data/eval_dataset_2026q1.duckdb`. A random replay check for AAPL on `2026-01-21`
  matched the live tool exactly.

The same balance-sheet payload is expected on later replay dates for a ticker because
the live yfinance balance-sheet endpoint exposes the latest available statement table,
not a daily historical statement feed.

Milestone 8 — Shared `get_cashflow` tool-output builder (2026-06-18). Added the
cash-flow statement writer that Plan B shares with Plan 07:

- `build_cashflow_outputs()` records `get_cashflow` payloads for each selected ticker
  on each SPY-derived transaction day.
- The payload is rendered through the existing
  `get_statement_text(ticker, "Cash flow statement", "cashflow")` helper, matching
  the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 54 passed.
- Live population wrote 183 `get_cashflow` rows to
  `data/eval_dataset_2026q1.duckdb`. A random replay check for AAPL on `2026-01-09`
  matched the live tool exactly.

The same cashflow payload is expected on later replay dates for a ticker because the
live yfinance cashflow endpoint exposes the latest available cash-flow statement table,
not a daily historical statement feed.

Milestone 9 — Plan B `fetch_stocktwits_messages` tool-output builder (2026-07-14).
Added the StockTwits replay writer needed for analyst sentiment replay:

- `build_stocktwits_outputs()` loads raw StockTwits pages from
  `data/raw-backtest/stocktwits`, dedupes messages by StockTwits message id, sorts
  newest-first, filters to each transaction day's 7-day lookback window, and writes
  prompt-ready `fetch_stocktwits_messages` rows.
- `render_stocktwits_payload()` preserves the live helper's output shape: bullish,
  bearish, unlabeled counts and percentages, followed by `[created_at · @user · tag]`
  message lines capped by `settings.sentiment.stocktwits_limit`.
- No StockTwits API call is made during dataset population; the builder consumes the
  local raw JSON files produced by the coverage scanner.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_trading_tools.py -q`
  reported 48 passed.
- Live population wrote 183 rows to `data/eval_dataset_2026q1.duckdb`, 61 each for
  AAPL, GOOGL, and AMZN over `2026-01-02..2026-03-31`, with zero no-data rows.
- Random parity check: GOOGL on `2026-02-12` used 1,804 raw messages in the 7-day
  window and selected the newest 30. The dataset payload exactly matched the live
  `fetch_stocktwits_messages` formatter when that helper was fed the same selected
  raw messages instead of calling the network.

Milestone 9 — Shared `get_income_statement` tool-output builder (2026-06-18). Added
the income-statement writer that Plan B shares with Plan 07:

- `build_income_statement_outputs()` records `get_income_statement` payloads for each
  selected ticker on each SPY-derived transaction day.
- The payload is rendered through the existing
  `get_statement_text(ticker, "Income statement", "income_stmt")` helper, matching
  the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 55 passed.
- Live population wrote 183 `get_income_statement` rows to
  `data/eval_dataset_2026q1.duckdb`. A random replay check for GOOGL on `2026-03-18`
  matched the live tool exactly.

The same income-statement payload is expected on later replay dates for a ticker because
the live yfinance income-statement endpoint exposes the latest available income
statement table, not a daily historical statement feed.

When the Plan B dataset and full run are complete, update this section with:

- the exact commands used;
- the number of trading days and first/last trading date observed;
- the CR for AAPL, GOOGL, and AMZN;
- whether any required source was missing or degraded;
- any difference from Plan 07 mechanics.


## Context and Orientation

This section assumes no prior knowledge of the repository. Read it before editing.

The project is a CrewAI reimplementation of TradingAgents. A crew is a team of language-model agents that run tasks in order. A flow chains crews together. The end-to-end flow lives in `src/trading_agents/main.py` as `TradingAgentsFlow`, which runs five stages in sequence and returns a final structured decision.

The five stages are:

1. Analyst stage, implemented in `src/trading_agents/crews/analyst_crew/analyst_crew.py`, produces four text reports: market, sentiment, news, and fundamentals. This is the only stage that calls external market, news, and social data sources.
2. Research stage, implemented in `src/trading_agents/crews/research_crew/research_crew.py`.
3. Trader stage, implemented in `src/trading_agents/crews/trader_crew/trader_crew.py`.
4. Risk stage, implemented in `src/trading_agents/crews/risk_management_crew/risk_management_crew.py`.
5. Portfolio stage, implemented in `src/trading_agents/crews/portfolio_crew/portfolio_crew.py`, returns a `PortfolioDecision` whose `rating` is exactly one of `Buy`, `Overweight`, `Hold`, `Underweight`, or `Sell`.

The flow takes a trigger payload, which is a small dictionary with `ticker` and `trade_date` as a `YYYY-MM-DD` string. The evaluation runs that flow once per ticker per transaction day, then converts the final portfolio rating into a simulated trade.

The ten data tools used by the analyst stage are:

- `get_stock_data` and `get_indicators` in `src/trading_agents/tools/market_data.py`;
- `get_news` and `get_global_news` in `src/trading_agents/tools/news.py`;
- `fetch_reddit_posts` and `fetch_stocktwits_messages` in `src/trading_agents/tools/sentiment.py`;
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` in `src/trading_agents/tools/fundamentals.py`.

How the analyst stage assembles its inputs is important for the evaluation seam. `prepare_analyst_inputs(inputs)` in `analyst_crew.py` normalizes `ticker`, reads `current_date` or `trade_date`, computes a seven-day default lookback window, and pre-fetches three text blocks directly: news sentiment, StockTwits, and Reddit. Those three text blocks feed the sentiment task. Other analyst tasks bind CrewAI tools directly.

Runtime configuration lives in `src/trading_agents/config/settings.py`. `AppSettings` uses the environment variable prefix `TRADING_AGENTS_` and nested delimiter `__`. That means `evaluation.start_date` is overridden by `TRADING_AGENTS_EVALUATION__START_DATE`, and `evaluation.dataset_path` is overridden by `TRADING_AGENTS_EVALUATION__DATASET_PATH`. `get_settings()` is cached with `functools.lru_cache`, so code that changes environment variables inside a Python process must call `get_settings.cache_clear()` before reading settings again.

Definitions used in this plan:

- Backtest window: `2026-01-01` through `2026-03-31` inclusive, the Plan B period over which decisions are made and CR is measured.
- Buffer: `2025-12-01` through `2025-12-31`, recorded so lookback windows before the first transaction day have source data.
- Transaction day, also called trading day: a date on which the exchange is open, identified by the presence of a benchmark SPY close price in the dataset.
- Prepared dataset: a DuckDB file holding recorded text output of every analyst tool for every ticker and trading day, plus daily close prices.
- Evaluation mode: a runtime mode where `settings.evaluation.enabled == True` and analyst tools read from the prepared dataset instead of live APIs.
- Cumulative return, abbreviated CR: the README metric `total_trading_profit / V_start * 100%`, where `V_start` is the larger of the first Buy close and the first Overweight close divided by `weight_over`, or `1` if neither Buy nor Overweight occurred.


## Plan of Work

This plan is intentionally smaller than Plan 07 because the architecture is already specified there. Do not fork the evaluator. Instead, implement or finish the shared evaluator pieces, then expose Plan B through Plan B-specific command names and artifacts.

First, keep the canonical defaults in `src/trading_agents/config/settings.py` unchanged. The defaults should continue to describe the 2024-Q1 README/paper period and `data/eval_dataset.duckdb`. Plan B dataset building is selected through `build-plan-b-eval-dataset`, not by taking over the reserved canonical `build-eval-dataset` name or changing settings defaults.

Second, ensure `build-plan-b-eval-dataset` uses the Plan B-specific dates and dataset path while still reading shared fields from `get_settings().evaluation`: `tickers`, `benchmark`, `price_tail_days`, `weight_over`, and `weight_under`. Keep the command name separate from `build-eval-dataset`, which is reserved for the original Plan 07 evaluation. Any hard-coded 2024 dates inside Plan B builder or runner code must be replaced by the Plan B constants or explicit Plan B options.

Third, build the Plan B dataset using the same source rules as Plan 07 except for Reddit availability: prices and indicators come from yfinance historical data; news and social blocks come from the existing historical source layer; Reddit is collected for the chosen 2026-Q1 period using the fixed RSS/request-volume handling from the scanner; and fundamentals remain best-effort current snapshots unless a point-in-time source has been added separately. There is no source-availability gate for Plan B.

When implementing the `get_stock_data` portion, include the default benchmark ticker,
SPY, in addition to AAPL, GOOGL, and AMZN. SPY is not just a calendar source: the
self-reflection portfolio manager uses benchmark-relative realized metrics, so the
Plan B dataset must contain SPY close prices and replayable `get_stock_data` payloads
wherever the evaluation may need benchmark history.

Treat the ten analyst data tools as ten separate builder sub-tasks, not as one monolith. Implement and validate `get_stock_data`, `get_indicators`, `get_news`, `get_global_news`, `fetch_reddit_posts`, `fetch_stocktwits_messages`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` one by one. If a source exposes a new failure mode while its payloads are being recorded, stop and resolve that source-specific issue before moving to the next tool. This is especially important for Reddit. The Plan B scanner in `plans/07b_reddit_coverage_scanner.md` found that Reddit HTTP 429s were caused by too many unauthenticated RSS requests from a cloud/datacenter IP, not a total IP block. A single request could return HTTP 200, but `3 tickers × 3 subreddits × 3 aliases = 27` requests exceeded Reddit's tight shared budget. The scanner fix OR-joined aliases into one query per `(ticker, subreddit)`, reducing volume from 27 requests to 9, and made 429s bounded and non-fatal by honoring `Retry-After` before falling back to fixed backoff. The scanner completed with `--delay 8`; the dataset builder should use at least 10 seconds between Reddit RSS requests to include a 2-second buffer. Reuse that lesson for any Reddit dataset ingestion path: minimize request volume, preserve structured statuses such as `ok`, `empty`, `blocked`, `rate_limited`, `timeout`, and `parse_error`, and never collapse access failures into ordinary "No data available" strings during verification.

After each dataset-building step is coded and validated with the needed focused tests,
run the corresponding builder and persist the collected rows into every applicable
DuckDB before marking the step complete. Code-only completion is not sufficient for
this evaluation plan: the dataset is being built alongside the implementation. For
shared sources, populate Plan B and Plan 07 unless the source is explicitly
Plan-B-only. The summary must be based on read-only queries against the DuckDB files
and must name the DuckDB file, tool name, tickers, covered date range, trading-day
count, per-tool row count, per-ticker row count where applicable, and any source
warnings. Wait for user feedback on that summary if the collected slice reveals
degraded or surprising data.

Current data-build reminder: Plan B and Plan 07 both have persistent `get_stock_data`
and `get_indicators` rows. The benchmark SPY needs `get_stock_data` payloads but does
not need `get_indicators` payloads.

Fourth, run the Plan B evaluator against `data/eval_dataset_2026q1.duckdb`. The runner must iterate transaction days chronologically because portfolio lessons accumulate over time. It must run every ticker on every transaction day and write reports under `output/eval/` or an equivalent isolated evaluation output directory.

Fifth, update this ExecPlan as work proceeds. If Plan B Reddit collection exposes a new failure mode despite the fixed 2026-Q1 path, do not silently drop Reddit. Record the failure in `Surprises & Discoveries`, leave Reddit payloads incomplete or absent, and stop before presenting a CR report until the issue is resolved.


## Concrete Steps

Run all commands from `/app/trading_agents`.

1. Confirm the Plan B dataset command resolves Plan B dates and path without changing
   Plan 07 defaults:

       uv run build-plan-b-eval-dataset --verify-only

   Expected:

       Evaluation dataset settings
       dataset_path: data/eval_dataset_2026q1.duckdb
       tickers: AAPL, GOOGL, AMZN
       benchmark: SPY
       window: 2026-01-01..2026-03-31
       buffer_start_date: 2025-12-01
       verify-only: dataset writes skipped

2. Verify the Plan B trading calendar:

       uv run python - <<'PY'
       import yfinance as yf
       for sym in ["SPY", "AAPL", "GOOGL", "AMZN"]:
           df = yf.download(sym, start="2026-01-01", end="2026-04-01", progress=False, auto_adjust=False)
           print(sym, len(df), df.index[0].date(), df.index[-1].date())
       PY

   Expected:

       SPY 61 2026-01-02 2026-03-31
       AAPL 61 2026-01-02 2026-03-31
       GOOGL 61 2026-01-02 2026-03-31
       AMZN 61 2026-01-02 2026-03-31

3. Run the focused tests for evaluation modules:

       uv run pytest tests/test_eval_backtest.py tests/test_eval_dataset.py tests/test_eval_exa_sources.py tests/test_eval_reddit_coverage.py

   Expected: all tests pass. If builder or runner tests have been added, include them in this command before marking this step complete.

4. Confirm the Plan B builder still resolves the chosen 2026-Q1 period before writing payloads:

       uv run build-plan-b-eval-dataset --verify-only

   Expected: resolved Plan B settings are printed and no DuckDB writes occur. This is
   not a source-availability gate. Reddit payloads are collected during the
   `fetch_reddit_posts` builder step using the fixed RSS/request-volume handling.

5. Build a small Plan B dataset slice:

       uv run build-plan-b-eval-dataset --tickers AAPL --limit-days 3

   Expected: `data/eval_dataset_2026q1.duckdb` exists and contains prices plus the implemented recorded tool outputs for AAPL over three transaction days. For each newly implemented builder, summarize the collected tool name, tickers, date range, trading-day count, row count, and warnings. `data/eval_dataset.duckdb` must not be created or modified by this Plan B command unless the run intentionally also collects the corresponding Plan 07 slice and reports that separately.

6. Run a Plan B smoke evaluation:

       TRADING_AGENTS_EVALUATION__START_DATE=2026-01-01 \
       TRADING_AGENTS_EVALUATION__END_DATE=2026-03-31 \
       TRADING_AGENTS_EVALUATION__BUFFER_START_DATE=2025-12-01 \
       TRADING_AGENTS_EVALUATION__DATASET_PATH=data/eval_dataset_2026q1.duckdb \
       uv run run-eval --tickers AAPL --limit-days 3

   Expected: the command writes an evaluation report showing each of the three AAPL transaction-day ratings and a CR value.

7. Build and run the full Plan B evaluation:

       uv run build-plan-b-eval-dataset

       TRADING_AGENTS_EVALUATION__START_DATE=2026-01-01 \
       TRADING_AGENTS_EVALUATION__END_DATE=2026-03-31 \
       TRADING_AGENTS_EVALUATION__BUFFER_START_DATE=2025-12-01 \
       TRADING_AGENTS_EVALUATION__DATASET_PATH=data/eval_dataset_2026q1.duckdb \
       uv run run-eval

   Expected: the final report gives CR for AAPL, GOOGL, and AMZN over 61 transaction days. Record those values in `Outcomes & Retrospective`.


## Validation and Acceptance

Acceptance is behavioral:

- Plan 07 defaults remain unchanged: importing `get_settings().evaluation` with no Plan B environment variables still returns `start_date='2024-01-01'`, `end_date='2024-03-29'`, and `dataset_path='data/eval_dataset.duckdb'`.
- `build-plan-b-eval-dataset --verify-only` resolves the Plan B dataset path and dates without environment overrides and without changing Plan 07 defaults.
- `uv run pytest tests/test_eval_backtest.py tests/test_eval_dataset.py tests/test_eval_exa_sources.py tests/test_eval_reddit_coverage.py` passes, along with any builder or runner tests added by Plan 07 implementation.
- `uv run build-plan-b-eval-dataset --verify-only` resolves Plan B settings and does not write payload rows. It is not a source-availability gate.
- `uv run build-plan-b-eval-dataset --tickers AAPL --limit-days 3` creates or refreshes only the Plan B dataset artifact.
- `uv run run-eval --tickers AAPL --limit-days 3` with Plan B overrides produces a rating list and CR value while reading analyst data from the Plan B dataset.
- The full Plan B run reports CR for AAPL, GOOGL, and AMZN over `2026-01-01..2026-03-31`, with transaction days `2026-01-02..2026-03-31`.


## Idempotence and Recovery

The Plan B dataset path is separate from the canonical Plan 07 dataset path. Rebuilding Plan B should use idempotent DuckDB upserts, so rerunning the builder refreshes rows instead of duplicating them. If any Plan B source build is interrupted after its code and tests pass, rerun the same Plan B command.

Plan B has no source-availability gate. The Reddit builder should still preserve structured statuses and fail clearly if the fixed 2026-Q1 collection path exposes a new access or parser failure; existing non-Reddit Plan B dataset rows should remain untouched.

The evaluation run should write only to an isolated evaluation output directory, such as `output/eval/`. Delete that directory to start a clean report run. Do not delete or rewrite ordinary `output/<ticker>_<date>/` artifacts as part of Plan B.

If a needed tool output is missing at evaluation time, the dataset reader should raise a clear error naming the tool, ticker, and date. Do not replace missing rows with empty strings.


## Artifacts and Notes

Representative Plan B source collection summary:

    Collected data/eval_dataset_2026q1.duckdb
    tool: fetch_reddit_posts
    tickers: AAPL, GOOGL, AMZN
    trading days: 61 (2026-01-02 .. 2026-03-31)
    tool_outputs rows: 183
    source statuses: ok=170 empty=13 rate_limited=0 blocked=0 timeout=0 parse_error=0
    notes: used OR-joined aliases and at least 10 seconds between Reddit RSS requests

Representative Plan B builder summary:

    Built data/eval_dataset_2026q1.duckdb
    tickers: AAPL, GOOGL, AMZN | benchmark: SPY
    trading days in window: 61 (2026-01-02 .. 2026-03-31)
    tool_outputs rows: 1830 | prices rows: 352

Representative Plan B evaluation report:

    TradingAgents Plan B evaluation — 2026-01-01..2026-03-31 (61 trading days)
    weight_over=0.5 weight_under=0.5 | language-model calls: 183 flow runs
    AAPL   CR = +3.8%
    GOOGL  CR = +6.4%
    AMZN   CR = +8.9%

The numbers above are illustrative placeholders. Replace them with actual output after the full run.

Known limitations: 2026-Q1 is selected for Reddit availability and is not the same market regime as 2024-Q1. Reddit coverage remains limited by the public RSS endpoint and may be biased toward the newest results returned by Reddit. Fundamentals and yfinance financial statements are best-effort latest snapshots unless a separate point-in-time fundamentals source has been implemented.


## Interfaces and Dependencies

Plan B should not introduce new public APIs unless the Plan 07 implementation still lacks date and dataset-path configurability. It depends on the same modules and libraries as Plan 07:

- `src/trading_agents/config/settings.py` provides `EvaluationSettings`.
- `src/trading_agents/evaluation/dataset.py` provides `EvalDataset`.
- `src/trading_agents/evaluation/backtest.py` provides the pure exchange simulator and CR calculation.
- `src/trading_agents/evaluation/exa_sources.py` provides historical news and social source helpers.
- `src/trading_agents/evaluation/build_dataset.py` provides shared builder code plus the `build-plan-b-eval-dataset` entry point; `build-eval-dataset` is registered for Plan 07 and uses the canonical 2024-Q1 settings defaults.
- `src/trading_agents/evaluation/run_eval.py` provides the `run-eval` entry point.
- `pyproject.toml` registers the console scripts.

These settings fields must still control shared Plan B behavior:

    EvaluationSettings.enabled
    EvaluationSettings.tickers
    EvaluationSettings.benchmark
    EvaluationSettings.price_tail_days
    EvaluationSettings.weight_over
    EvaluationSettings.weight_under

The Plan B builder command itself owns these Plan B-specific defaults:

    start_date=2026-01-01
    end_date=2026-03-31
    buffer_start_date=2025-12-01
    dataset_path=data/eval_dataset_2026q1.duckdb

Revision Note: 2026-06-16 Initial Plan B ExecPlan drafted after the Reddit coverage scanner ranked 2026-Q1 first and yfinance confirmed 61 trading days for SPY, AAPL, GOOGL, and AMZN from 2026-01-02 through 2026-03-31. This plan intentionally keeps Plan 07 as the canonical 2024-Q1 evaluation and uses a separate Plan B dataset artifact.

Revision Note: 2026-06-17 Implemented and documented the shared yfinance price-table
builder for Plan B and Plan 07. The Plan B smoke build now creates the isolated
`data/eval_dataset_2026q1.duckdb` price table for AAPL plus SPY; analyst tool outputs
and evaluation runs remain pending.

Revision Note: 2026-06-17 Clarified per user direction that Plan B has no
source-availability gate because the fixed scanner/retrieval path can retrieve Reddit
posts during the chosen 2026-Q1 backtest period. Plan B `fetch_reddit_posts` should be
implemented, tested, collected, and summarized like the other source builders, while
preserving structured source statuses and rate-limit handling.
