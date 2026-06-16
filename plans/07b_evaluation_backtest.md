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
- [ ] (pending) Implement the shared price-table and trading-day calendar build for Plan B: write close prices for AAPL, GOOGL, AMZN, and the default benchmark ticker, SPY, into `data/eval_dataset_2026q1.duckdb` before recording per-tool payloads.
- [ ] (pending) Implement Plan B dataset building for `get_stock_data`: record the market-data text block for AAPL, GOOGL, AMZN, and SPY on each trading day using the same lookback window the analyst stage will request; SPY history is required by the portfolio manager's self-reflection and benchmark-relative realized-return calculations.
- [ ] (pending) Implement Plan B dataset building for `get_indicators`: record the indicator text block for each ticker and trading day using the same indicator list and lookback window as the analyst stage.
- [ ] (pending) Implement Plan B dataset building for `get_news`: record ticker-news text through the historical source layer and preserve the live tool's output shape.
- [ ] (pending) Implement Plan B dataset building for `get_global_news`: record global-market-news text through the historical source layer for each trading day.
- [ ] (pending) Implement Plan B dataset building for `fetch_reddit_posts`: record Reddit sentiment text with explicit handling for rate limits, blocked access, empty results, and parse failures.
- [ ] (pending) Implement Plan B dataset building for `fetch_stocktwits_messages`: record StockTwits sentiment text and distinguish empty results from source access failures where possible.
- [ ] (pending) Implement Plan B dataset building for `get_fundamentals`: record best-effort fundamentals text for each ticker and trading day.
- [ ] (pending) Implement Plan B dataset building for `get_balance_sheet`: record best-effort balance-sheet text for each ticker and trading day.
- [ ] (pending) Implement Plan B dataset building for `get_cashflow`: record best-effort cashflow text for each ticker and trading day.
- [ ] (pending) Implement Plan B dataset building for `get_income_statement`: record best-effort income-statement text for each ticker and trading day.
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

Third, build the Plan B dataset using the same source rules as Plan 07. Prices and indicators come from yfinance historical data. News and social blocks come from the existing historical source layer, with Reddit treated as required. Fundamentals remain best-effort current snapshots unless a point-in-time source has been added separately.

When implementing the `get_stock_data` portion, include the default benchmark ticker,
SPY, in addition to AAPL, GOOGL, and AMZN. SPY is not just a calendar source: the
self-reflection portfolio manager uses benchmark-relative realized metrics, so the
Plan B dataset must contain SPY close prices and replayable `get_stock_data` payloads
wherever the evaluation may need benchmark history.

Treat the ten analyst data tools as ten separate builder sub-tasks, not as one monolith. Implement and validate `get_stock_data`, `get_indicators`, `get_news`, `get_global_news`, `fetch_reddit_posts`, `fetch_stocktwits_messages`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` one by one. If a source exposes a new failure mode while its payloads are being recorded, stop and resolve that source-specific issue before moving to the next tool. This is especially important for Reddit. The Plan B scanner in `plans/07b_reddit_coverage_scanner.md` found that Reddit HTTP 429s were caused by too many unauthenticated RSS requests from a cloud/datacenter IP, not a total IP block. A single request could return HTTP 200, but `3 tickers × 3 subreddits × 3 aliases = 27` requests exceeded Reddit's tight shared budget. The scanner fix OR-joined aliases into one query per `(ticker, subreddit)`, reducing volume from 27 requests to 9, and made 429s bounded and non-fatal by honoring `Retry-After` before falling back to fixed backoff. The scanner completed with `--delay 8`; the dataset builder should use at least 10 seconds between Reddit RSS requests to include a 2-second buffer. Reuse that lesson for any Reddit dataset ingestion path: minimize request volume, preserve structured statuses such as `ok`, `empty`, `blocked`, `rate_limited`, `timeout`, and `parse_error`, and never collapse access failures into ordinary "No data available" strings during verification.

Fourth, run the Plan B evaluator against `data/eval_dataset_2026q1.duckdb`. The runner must iterate transaction days chronologically because portfolio lessons accumulate over time. It must run every ticker on every transaction day and write reports under `output/eval/` or an equivalent isolated evaluation output directory.

Fifth, update this ExecPlan as work proceeds. If the source availability gate fails for Plan B, do not silently drop Reddit. Record the failure in `Surprises & Discoveries`, leave the dataset incomplete or absent, and stop before presenting a CR report.


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

4. Verify Plan B source availability before writing the dataset. This needs `EXA_API_KEY` and network access:

       uv run build-plan-b-eval-dataset --verify-only

   Expected success: a compact source-by-source report showing ticker news, global news, Reddit, and StockTwits available for the Plan B probe window, followed by zero exit code and no DuckDB writes.

   Expected failure: a nonzero exit with a report naming the unavailable source. If Reddit is unavailable, stop and update this plan. Do not build a no-Reddit Plan B dataset under this plan.

5. Build a small Plan B dataset slice:

       uv run build-plan-b-eval-dataset --tickers AAPL --limit-days 3

   Expected: `data/eval_dataset_2026q1.duckdb` exists and contains prices plus recorded tool outputs for AAPL over three transaction days. `data/eval_dataset.duckdb` must not be created or modified by this command unless it already existed for Plan 07 and is untouched.

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
- `uv run build-plan-b-eval-dataset --verify-only` checks source availability before creating or modifying `data/eval_dataset_2026q1.duckdb`.
- `uv run build-plan-b-eval-dataset --tickers AAPL --limit-days 3` creates or refreshes only the Plan B dataset artifact.
- `uv run run-eval --tickers AAPL --limit-days 3` with Plan B overrides produces a rating list and CR value while reading analyst data from the Plan B dataset.
- The full Plan B run reports CR for AAPL, GOOGL, and AMZN over `2026-01-01..2026-03-31`, with transaction days `2026-01-02..2026-03-31`.


## Idempotence and Recovery

The Plan B dataset path is separate from the canonical Plan 07 dataset path. Rebuilding Plan B should use idempotent DuckDB upserts, so rerunning the builder refreshes rows instead of duplicating them. If the build is interrupted after source verification passes, rerun the same Plan B command.

The source availability check must run before DuckDB writes. If `EXA_API_KEY` is missing, or if ticker news, global news, Reddit, or StockTwits is unavailable for the Plan B probe window, the builder should fail clearly and leave the Plan B dataset untouched.

The evaluation run should write only to an isolated evaluation output directory, such as `output/eval/`. Delete that directory to start a clean report run. Do not delete or rewrite ordinary `output/<ticker>_<date>/` artifacts as part of Plan B.

If a needed tool output is missing at evaluation time, the dataset reader should raise a clear error naming the tool, ticker, and date. Do not replace missing rows with empty strings.


## Artifacts and Notes

Representative Plan B source scan:

    Source availability check — 2025-12-01..2025-12-10
    AAPL  news available | reddit available | stocktwits available
    GOOGL news available | reddit available | stocktwits available
    AMZN  news available | reddit available | stocktwits available
    global_news available
    OK: required sources available; dataset may be built

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

Known limitations: 2026-Q1 is selected for Reddit availability and is not the same market regime as 2024-Q1. Reddit coverage remains limited by the public RSS endpoint and may be biased toward the newest results returned by Reddit. Fundamentals are best-effort snapshots unless a separate point-in-time fundamentals source has been implemented.


## Interfaces and Dependencies

Plan B should not introduce new public APIs unless the Plan 07 implementation still lacks date and dataset-path configurability. It depends on the same modules and libraries as Plan 07:

- `src/trading_agents/config/settings.py` provides `EvaluationSettings`.
- `src/trading_agents/evaluation/dataset.py` provides `EvalDataset`.
- `src/trading_agents/evaluation/backtest.py` provides the pure exchange simulator and CR calculation.
- `src/trading_agents/evaluation/exa_sources.py` provides historical news and social source helpers.
- `src/trading_agents/evaluation/build_dataset.py` provides the `build-plan-b-eval-dataset` entry point; `build-eval-dataset` remains reserved for Plan 07.
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
