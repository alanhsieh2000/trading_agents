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
- [ ] (pending) Create the `build-eval-dataset` entry point with a Reddit-specific availability/status gate in `src/trading_agents/evaluation/build_dataset.py`; this gate belongs to the `fetch_reddit_posts` builder step only and must not block implementation or collection for non-Reddit tools.
- [x] (2026-06-17 00:00Z) Implemented the shared price-table and trading-day calendar build in `build_dataset.py`: write close prices for the selected evaluation tickers and the default benchmark ticker, SPY, before recording per-tool payloads.
- [x] (2026-06-17 06:37Z) Implemented and populated shared dataset building for `get_stock_data`: recorded the market-data text block for each evaluation ticker and for SPY on each trading day using the same lookback window the analyst stage will request; SPY history is required by the portfolio manager's self-reflection and benchmark-relative realized-return calculations. Wrote 244 persistent `get_stock_data` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, SPY 61.
- [x] (2026-06-17) Implemented and populated dataset building for `get_indicators`: records all allowed indicators from `src/trading_agents/tools/market_data.py` for each configured ticker and trading day using the analyst-stage lookback window. Wrote 183 persistent `get_indicators` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero SPY indicator rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison matched for `AMZN` on `2024-02-27` with 12 indicators.
- [x] (2026-06-17 13:03Z) Implemented and populated shared dataset building for `get_news`: records ticker-news text through the Exa historical source layer with the same markdown/no-news/error contract as the live Yahoo-backed tool. The builder uses a doubled news limit (`settings.news.ticker_limit * 2`, currently 40) for buffer coverage, writes ticker rows only, and shares the same implementation with Plan B. Wrote 183 persistent `get_news` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero error payloads and zero no-news fallback rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AMZN on `2024-03-05`; the evaluation-backed `get_news` tool matched the DuckDB payload exactly and returned 39 articles for `2024-02-27..2024-03-05`.
- [x] (2026-06-17) Implemented and populated shared dataset building for `get_global_news`: records one Exa historical global-market-news payload per trading day, stores it under each evaluated ticker key for existing dataset-backed tool replay, and uses a doubled global-news limit (`settings.news.global_limit * 2`, currently 20). Wrote 183 persistent `get_global_news` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero error payloads and zero no-news fallback rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-03-21`; the evaluation-backed `get_global_news` tool matched the DuckDB payload exactly and returned the shared global payload for all ticker keys on that date.
- [ ] (pending) Implement dataset building for `fetch_reddit_posts`: record Reddit sentiment text with explicit handling for rate limits, blocked access, empty results, and parse failures. This is the only pending dataset-building step that is gated by source-availability/status verification.
- [ ] (pending) Implement dataset building for `fetch_stocktwits_messages`: record StockTwits sentiment text and distinguish empty results from source access failures where possible.
- [x] Implement dataset building for `get_fundamentals`: record best-effort fundamentals text for each ticker and trading day.
- [x] (2026-06-18 14:16Z) Implemented and populated shared dataset building for `get_balance_sheet`: records the yfinance latest balance-sheet statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_balance_sheet` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-03-08`; the evaluation-backed `get_balance_sheet` tool matched the live tool exactly and AAPL had one distinct payload across all 61 replay dates.
- [x] (2026-06-18 14:24Z) Implemented and populated shared dataset building for `get_cashflow`: records the yfinance latest cash flow statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_cashflow` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-01-12`; the evaluation-backed `get_cashflow` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [x] (2026-06-18 14:30Z) Implemented and populated shared dataset building for `get_income_statement`: records the yfinance latest income statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_income_statement` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AMZN on `2024-02-28`; the evaluation-backed `get_income_statement` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [ ] (pending) If the Reddit availability/status gate fails for the configured 2024-Q1 evaluation, scan candidate replacement periods and record findings before recording Reddit payloads.
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
- Observation: The original TradingAgents repository works around Reddit JSON
  blocking by using Reddit RSS/Atom search first.
  Evidence: `https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/dataflows/reddit.py`
  documents that `/search.json` is WAF-blocked for public clients and fetches
  `/search.rss` by default. A local probe on 2026-06-15 for
  `https://www.reddit.com/r/wallstreetbets/search.rss?q=AAPL&restrict_sr=on&sort=new&t=week&limit=5`
  returned HTTP 200 with two Atom entries dated 2026-06-10 and 2026-06-09. This is
  useful for fixing live Reddit fetching, but it still does not provide exact
  historical date-range access for the 2024-Q1 backtest.
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
- Observation: The Plan B Reddit coverage scanner could not complete a live ranked
  recommendation in this environment because Reddit repeatedly returned HTTP 429.
  Evidence: `uv run scan-reddit-coverage --delay 3` on 2026-06-16 repeatedly printed
  warnings such as `HTTP 429; retrying in 10s`, `20s`, and `40s` for AAPL Reddit RSS
  queries and was manually stopped before a ranking was printed. A fallback
  `timeout 600 uv run scan-reddit-coverage --delay 10` attempt also repeatedly hit
  HTTP 429 retry warnings and was manually stopped before completion, so no Plan B
  quarter recommendation was recorded.
- Observation (2026-06-16, resolved): The HTTP 429 root cause was **request volume
  against the unauthenticated `www.reddit.com` RSS endpoint from this GCP datacenter
  IP**, not an IP block. A single live request still returns HTTP 200
  (`curl .../r/wallstreetbets/search.rss?q=AAPL&...&t=year&limit=100` → 200, 100
  entries spanning 2025-08-07..2026-06-10), but the scanner fired
  `3 tickers × 3 subreddits × 3 query aliases = 27` sequential requests, far above
  Reddit's tight shared budget for cloud IPs, so 429s cascaded. The original
  `fetch_rss_posts` also ignored the `Retry-After` header.
  Fix: `fetch_all_posts` now OR-joins the alias tuple into one query per
  (ticker, subreddit) (`27 → 9` requests) and `fetch_rss_posts` honors `Retry-After`
  (capped 60s) before falling back to the fixed 10/20/40s backoff. The successful
  scanner run used `--delay 8`; use **at least 10 seconds between Reddit RSS
  requests** in dataset ingestion to add a 2-second safety buffer. 429s still occur
  on this datacenter IP but are now **non-fatal**: bounded retries then continue, so
  the run terminates with usable partial coverage instead of hanging. Reliably
  eliminating 429 would require Reddit OAuth (`oauth.reddit.com`, 100 req/min), which
  is out of scope here.
- Observation (2026-06-16): The fixed scanner completed and ranked the candidate
  quarters; **Recommended Plan B period: 2026-Q1**.
  Evidence: `uv run python -m trading_agents.evaluation.reddit_coverage --delay 8`
  printed:
  `1. 2026-Q1: posts=176, >=1 coverage=82.0%, >=3 coverage=71.6%, min ticker coverage=50.8%, pairs=6/9`
  `2. 2025-Q4: posts=31, >=1 coverage=21.9%, >=3 coverage=13.0%, min ticker coverage=0.0%, pairs=3/9`
  `3. 2025-Q3: posts=0, >=1 coverage=0.0%, >=3 coverage=0.0%, min ticker coverage=0.0%, pairs=0/9`.
  Caveat: coverage skews to recent quarters because Reddit RSS returns only the 100
  newest posts per query (`t=year&limit=100`, no pagination), reaching back only to
  ~Aug 2025; 2025-Q3 is effectively unreachable. The 2026-Q1 recommendation reflects
  data-availability recency, not necessarily superior historical sentiment depth.
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
  dataset and make source availability/status verification specific to the
  `fetch_reddit_posts` builder step.
  Rationale: The README evaluation lists Reddit among the analyst data sources, and the
  user confirmed that missing Reddit should not be silently accepted. The user clarified
  on 2026-06-17 that the availability gate is for Reddit only; other dataset builders
  such as prices, indicators, news, StockTwits, and fundamentals should be implemented,
  tested, and collected without waiting for the Reddit gate.
  Date/Author: 2026-06-12 / Codex (confirmed with the user)

- Decision: The evaluation dataset builder must record Reddit probe status separately
  from Reddit result count.
  Rationale: `No data available for Reddit posts ...` is ambiguous in the current live
  tool: it can mean zero matching posts, HTTP 403 blocking, timeout, JSON parse
  failure, or another network error. Plan 07's availability gate needs structured
  statuses such as `ok`, `empty`, `blocked`, `timeout`, and `parse_error` so it fails
  for source access problems instead of misclassifying them as empty data.
  Date/Author: 2026-06-15 / Codex

- Decision: Track the RSS-first live Reddit fix in Plan 01, but keep Plan 07's
  historical Reddit requirement separate.
  Rationale: RSS-first fetching should repair the current live `fetch_reddit_posts`
  behavior and can make recent Reddit diagnostics more trustworthy. It does not
  replace the Plan 07 requirement for historical, date-bounded Reddit data, so the
  evaluation builder must still use Exa or another historical provider plus structured
  availability statuses.
  Date/Author: 2026-06-15 / Codex

- Decision: Select any Plan B backtest quarter by Reddit ticker-day coverage, not by
  raw Reddit post count.
  Rationale: A quarter with many posts for one ticker is not useful if the other
  evaluation tickers have sparse sentiment evidence. The Plan B scanner ranks
  2025-Q3, 2025-Q4, and 2026-Q1 by the share of ticker trading days whose 7-day
  lookback window has at least one Reddit post, then by stricter >=3-post coverage,
  minimum per-ticker coverage, and total posts.
  Date/Author: 2026-06-15 / Codex

- Decision: Split dataset-builder progress by the ten analyst data tools.
  Rationale: The Reddit HTTP 429 investigation showed that each data source can fail
  for a different operational reason: request volume, provider rate limits, blocked
  endpoints, empty historical coverage, parser errors, or stale API assumptions. The
  builder should be implemented and validated one tool at a time so each source-specific
  issue is diagnosed and fixed without hiding it inside a single broad "build dataset"
  task.
  Date/Author: 2026-06-16 / Codex

- Decision: Share the price-table and trading-calendar builder between Plan 07 and
  Plan B, with the CLI wrappers supplying only different default periods and dataset
  paths.
  Rationale: Close-price recording and benchmark-derived transaction days are identical
  mechanics for both evaluations. Keeping this in one `build_price_table()` path avoids
  drift between the canonical 2024-Q1 evaluation and the 2026-Q1 Plan B fallback.
  Date/Author: 2026-06-17 / Codex

- Decision: After each non-Reddit dataset-builder step is implemented and validated
  with focused tests, immediately collect that tool's data into the corresponding
  DuckDB files and summarize the collected coverage for user feedback.
  Rationale: Incremental collection lets the user review each source slice before the
  full dataset is complete. It also avoids treating the Reddit gate as a blocker for
  unrelated tools.
  Date/Author: 2026-06-17 / Codex (user direction)

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

Milestone 3 — Reddit availability/status gate (planned next for Reddit only). The
`fetch_reddit_posts` builder must verify Reddit source status before recording Reddit
payloads. The gate checks the relevant probe window and preserves structured statuses
such as `ok`, `empty`, `blocked`, `rate_limited`, `timeout`, and `parse_error`. If
Reddit is unavailable or access is degraded, the command exits nonzero with a compact
Reddit report and leaves Reddit `tool_outputs` rows untouched. This gate does not block
non-Reddit builders.

Milestone 4 — Shared price table and calendar builder (2026-06-17). Added the first
write phase of `src/trading_agents/evaluation/build_dataset.py` for both evaluation
periods:

- `build_price_table()` downloads yfinance close prices from the configured buffer
  start through the configured evaluation end plus `price_tail_days`, writes them
  idempotently through `EvalDataset.put_prices()`, and derives transaction days from
  the benchmark ticker.
- The price symbols are the selected evaluation tickers plus the benchmark, with
  duplicates removed, so a smoke run such as `--tickers AAPL` still records SPY.
- `pyproject.toml` now registers `build-eval-dataset` for the canonical Plan 07
  defaults and keeps `build-plan-b-eval-dataset` for the Plan B defaults.
- Focused validation: `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py`
  passed with 23 tests. `uv run build-eval-dataset --verify-only` printed
  `data/eval_dataset.duckdb` and `2024-01-01..2024-03-29`, confirming Plan 07
  defaults remain unchanged.

At this milestone, the Reddit availability/status gate and all analyst tool-output
writers were still pending.

Milestone 5 — Shared `get_stock_data` tool-output builder (2026-06-17). Added the
first analyst tool-output writer in the same shared builder path used by Plan 07 and
Plan B:

- `build_stock_data_outputs()` records `get_stock_data` payloads for each selected
  ticker plus SPY on each benchmark transaction day, keyed by
  `(tool_name, ticker, as_of_date)` through `EvalDataset.put_tool_output()`.
- Each payload is rendered by the existing `get_stock_data_text()` helper with
  `start_date = as_of_date - settings.analyst_stage.lookback_days` and
  `end_date = as_of_date`, matching the analyst-stage `prepare_analyst_inputs()`
  window.
- The CLI summary now reports `get_stock_data outputs built`, payload count,
  symbol list, transaction-day range, and `lookback_days`; remaining tool-output
  builders are still marked pending.
- Focused validation: `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py`
  passed with 24 tests.

Remaining builder work: the Reddit availability/status gate must run before Reddit
payload writes, and the nine remaining analyst tool-output writers remain pending.
Non-Reddit writers should be implemented, tested, collected into DuckDB, and
summarized independently of the Reddit gate.

Milestone 6 — Shared `get_balance_sheet` tool-output builder (2026-06-18). Added the
first financial-statement writer in the shared builder path used by Plan 07 and Plan B:

- `build_snapshot_tool_outputs()` centralizes the "fetch once per ticker, write every
  transaction day" behavior used by current-snapshot fundamentals and statement tools.
- `build_balance_sheet_outputs()` records `get_balance_sheet` payloads for each
  selected ticker on each benchmark transaction day, keyed by
  `(tool_name, ticker, as_of_date)` through `EvalDataset.put_tool_output()`.
- The payload is rendered through the existing `get_statement_text(ticker, "Balance sheet", "balance_sheet")`
  helper, matching the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 53 passed.
- Live population wrote 183 `get_balance_sheet` rows to `data/eval_dataset.duckdb`.
  A random replay check for AAPL on `2024-03-08` matched the live tool exactly.

The same balance-sheet payload is expected on later replay dates for a ticker because
the live yfinance balance-sheet endpoint exposes the latest available statement table,
not a daily historical statement feed.

Milestone 7 — Shared `get_cashflow` tool-output builder (2026-06-18). Added the
cash-flow statement writer in the shared builder path used by Plan 07 and Plan B:

- `build_cashflow_outputs()` records `get_cashflow` payloads for each selected ticker
  on each benchmark transaction day, keyed by `(tool_name, ticker, as_of_date)`.
- The payload is rendered through the existing
  `get_statement_text(ticker, "Cash flow statement", "cashflow")` helper, matching
  the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 54 passed.
- Live population wrote 183 `get_cashflow` rows to `data/eval_dataset.duckdb`.
  A random replay check for AAPL on `2024-01-12` matched the live tool exactly.

The same cashflow payload is expected on later replay dates for a ticker because the
live yfinance cashflow endpoint exposes the latest available cash-flow statement table,
not a daily historical statement feed.

Milestone 8 — Shared `get_income_statement` tool-output builder (2026-06-18). Added
the income-statement writer in the shared builder path used by Plan 07 and Plan B:

- `build_income_statement_outputs()` records `get_income_statement` payloads for each
  selected ticker on each benchmark transaction day, keyed by
  `(tool_name, ticker, as_of_date)`.
- The payload is rendered through the existing
  `get_statement_text(ticker, "Income statement", "income_stmt")` helper, matching
  the live tool's text format.
- Focused validation passed:
  `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`
  reported 55 passed.
- Live population wrote 183 `get_income_statement` rows to `data/eval_dataset.duckdb`.
  A random replay check for AMZN on `2024-02-28` matched the live tool exactly.

The same income-statement payload is expected on later replay dates for a ticker because
the live yfinance income-statement endpoint exposes the latest available income
statement table, not a daily historical statement feed.


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
  (2023-12-01..2023-12-10) and sampled 2024-Q1 windows. The source-availability gate
  applies only to the `fetch_reddit_posts` builder step. Other tools are not gated by
  this check and should be implemented, tested, collected into DuckDB, and summarized
  independently.


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
`build-eval-dataset` console entry point and shared functions for each tool-specific
dataset slice. The builder should download daily closes for each ticker and the
benchmark over `buffer_start_date … end_date + price_tail_days`, fill `prices`, and
derive the trading-day list from the benchmark price index within the window. For each
ticker × trading day, the tool-specific builders record into `tool_outputs` the text
from `get_stock_data_text`/`get_indicators_text` (called with the same
`start = trade_date − lookback_days`, `end = trade_date` the eval flow uses), the Exa
news and global-news blocks, the Exa StockTwits block, the Exa or RSS Reddit block, and
best-effort fundamentals/statement text. Use `EvalDataset.put_prices()` and
`put_tool_output()` so the build is idempotent. Support `--tickers`, `--limit-days`,
and `--verify-only`; if `--scan-periods` is kept, it is Reddit-focused and must not
change `EvaluationSettings.start_date` or `end_date`.

The availability/status gate is not a global builder phase. It belongs only to the
`fetch_reddit_posts` builder step because Reddit is required and has known historical
coverage and rate-limit failure modes. That step checks the relevant source window,
preserves structured statuses such as `ok`, `empty`, `blocked`, `rate_limited`,
`timeout`, and `parse_error`, and stops before recording misleading Reddit payloads when
source access is not usable. The gate must not prevent the other nine analyst tools from
being implemented or collected.

When implementing the `get_stock_data` portion, include the default benchmark ticker,
SPY, in addition to AAPL, GOOGL, and AMZN. SPY is not just a calendar source: the
self-reflection portfolio manager uses benchmark-relative realized metrics, so the
dataset must contain SPY close prices and replayable `get_stock_data` payloads wherever
the evaluation may need benchmark history.

Treat the ten analyst data tools as ten separate builder sub-tasks, not as one monolith.
Implement and validate `get_stock_data`, `get_indicators`, `get_news`,
`get_global_news`, `fetch_reddit_posts`, `fetch_stocktwits_messages`,
`get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and
`get_income_statement` one by one. If a source exposes a new failure mode while its
payloads are being recorded, stop and resolve that source-specific issue before moving
to the next tool. This is especially important for Reddit. The Plan B scanner in
`plans/07b_reddit_coverage_scanner.md` found that Reddit HTTP 429s were caused by too
many unauthenticated RSS requests from a cloud/datacenter IP, not a total IP block. A
single request could return HTTP 200, but `3 tickers × 3 subreddits × 3 aliases = 27`
requests exceeded Reddit's tight shared budget. The scanner fix OR-joined aliases into
one query per `(ticker, subreddit)`, reducing volume from 27 requests to 9, and made
429s bounded and non-fatal by honoring `Retry-After` before falling back to fixed
backoff. The scanner completed with `--delay 8`; the dataset builder should use **at
least 10 seconds between Reddit RSS requests** to include a 2-second buffer. Reuse that
lesson for any Reddit dataset ingestion path: minimize request volume, preserve
structured statuses such as `ok`, `empty`, `blocked`, `rate_limited`, `timeout`, and
`parse_error`, and never collapse access failures into ordinary "No data available"
strings during verification.

After each dataset-building step is coded and validated with the needed focused tests,
run the corresponding builder and persist the collected rows into every applicable
DuckDB before marking the step complete. Code-only completion is not sufficient for
this evaluation plan: the dataset is being built alongside the implementation. The
summary must be based on read-only queries against the DuckDB files and must name the
DuckDB file, tool name, tickers, date range, trading-day count, per-tool row count,
per-ticker row count where applicable, and any source warnings. After the user reviews
that summary, incorporate any feedback before moving to the next dataset source.

Current data-build reminder: the Plan 07 DuckDB has persistent `get_stock_data` and
`get_indicators` rows. The benchmark SPY needs `get_stock_data` payloads but does not
need `get_indicators` payloads.

Before changing the configured backtest dates for Plan B, run
`uv run scan-reddit-coverage`. Treat its recommended quarter as the candidate
Plan B period only if every ticker has nonzero coverage and the coverage table is
recorded in this plan. If Reddit coverage is concentrated in a single ticker,
prefer a no-Reddit ablation or continue waiting for Exa historical Reddit access
instead of pretending the quarter is equivalent to the canonical evaluation.

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

4. Before building the Reddit payloads, verify Reddit source availability/status (needs
   the configured Reddit historical source and network):

       uv run build-eval-dataset --verify-only

   Expected if Reddit is usable: a Reddit-focused report showing usable status for each
   ticker over the configured probe window, followed by a zero exit code and no Reddit
   payload writes when `--verify-only` is used.

   Expected if Reddit remains unavailable: a nonzero exit with a report naming the
   missing Reddit rows, for example `AAPL reddit unavailable for 2023-12-01..2023-12-10`.
   In this case, stop the `fetch_reddit_posts` builder step and do not record misleading
   Reddit payloads. This does not block collecting non-Reddit tool outputs. Use the scan
   command below to search for a viable replacement period:

       uv run build-eval-dataset --scan-periods

   Expected scan behavior: print candidate windows and Reddit coverage/status. Do not
   update settings or write the dataset automatically.

5. Build each small dataset slice after its code and focused tests pass:

       uv run build-eval-dataset --tickers AAPL --limit-days 3

   Expected for non-Reddit builders: collect the implemented source slice immediately
   without waiting for the Reddit gate, then print a summary naming the DuckDB file, tool
   name, tickers, covered trading days, row count, and warnings. Expected for the Reddit
   builder: collect only after the Reddit availability/status gate succeeds.

   When a new source builder is complete, run it for both Plan 07 and Plan B if the
   source applies to both datasets, then summarize both collected slices for user
   feedback. Inspect with:

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
  passes after the builder is added. The builder tests must mock Exa/yfinance/Reddit as
  needed and assert that Reddit verification failure prevents Reddit payload writes.
- `uv run build-eval-dataset --verify-only` performs the Reddit-specific status check
  for the `fetch_reddit_posts` builder. If Reddit is unavailable, the command exits
  nonzero with a clear report and does not create or update Reddit `tool_outputs` rows.
  Non-Reddit builders are not blocked by this check.
- `uv run build-eval-dataset --tickers AAPL --limit-days 3` produces a DuckDB file with
  the expected implemented `tool_outputs` and `prices` rows, and is idempotent (running
  it twice does not duplicate rows). For each newly implemented non-Reddit source, data
  collection can proceed as soon as its code and tests pass.
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

The Reddit availability/status gate runs before writing Reddit `tool_outputs` rows. If
Reddit is unavailable for the required probe window, the Reddit builder fails with a
clear report and leaves existing non-Reddit dataset rows intact. Missing or degraded
Reddit must not block collection for prices, `get_stock_data`, `get_indicators`,
`get_news`, `get_global_news`, `fetch_stocktwits_messages`, or fundamentals/statement
tools. `--verify-only` and `--scan-periods` are read-only with respect to Reddit writes.

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

    Reddit availability/status check — 2023-12-01..2023-12-10
    AAPL  reddit unavailable
    GOOGL reddit unavailable
    AMZN  reddit unavailable
    ERROR: Reddit unavailable; Reddit payloads were not written. Non-Reddit builders may still run.

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

Known limitations to keep in mind: fundamentals and yfinance financial statements are
best-effort latest snapshots, not point-in-time daily history; the trading-day count is
derived from the actual price calendar and equals the README's 61 (2024-01-02 ..
2024-03-28, with 2024-03-29 a closed holiday); Reddit is currently the likely
historical-source blocker; and the full run is language-model-expensive (3 × 61 = 183
flow runs), which is why `--limit-days` exists.


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
    def verify_reddit_availability(tickers: list[str]) -> "AvailabilityReport": ...
    def build_dataset(tickers: list[str], limit_days: int | None = None) -> "BuildSummary": ...
    def build_price_table(options: "BuildDatasetOptions", dataset: EvalDataset) -> "PriceBuildResult": ...

`main()` parses `--verify-only`, `--tickers`, `--limit-days`, and `--scan-periods`.
`verify_reddit_availability()` must return enough structured data for tests to assert
which Reddit status failed, and `main()` must return a nonzero exit code when Reddit is
unavailable for the Reddit builder step. `build_dataset()` and the non-Reddit builders
must not depend on Reddit verification.

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
global-news, and StockTwits results but no Reddit results. This broad gate wording was
superseded on 2026-06-17: the availability/status gate applies only to
`fetch_reddit_posts`, and non-Reddit builders can collect data independently.

Revision Note: 2026-06-17 Implemented and documented the shared yfinance price-table
builder used by both Plan 07 and Plan B. This records buffered close prices and
benchmark transaction days but does not complete the historical source gate or analyst
tool-output recording.

Revision Note: 2026-06-17 Clarified per user direction that the availability/status gate
is only for `fetch_reddit_posts`. Non-Reddit dataset builders are not gated; once each
builder is implemented and validated with focused tests, collect that slice into the
corresponding DuckDB file(s) and summarize the collected coverage for user feedback.
