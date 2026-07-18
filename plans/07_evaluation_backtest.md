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
- [x] (2026-07-17 08:02Z) Completed the `build-eval-dataset` entry point in `src/trading_agents/evaluation/build_dataset.py`, including offline validation and ingestion of both canonical social archives under `data/raw-backtest/`. Canonical social preparation makes no Reddit, StockTwits, Exa, or Arctic Shift requests; Plan B retains its separate live Reddit RSS behavior.
- [x] (2026-06-17 00:00Z) Implemented the shared price-table and trading-day calendar build in `build_dataset.py`: write close prices for the selected evaluation tickers and the default benchmark ticker, SPY, before recording per-tool payloads.
- [x] (2026-06-17 06:37Z) Implemented and populated shared dataset building for `get_stock_data`: recorded the market-data text block for each evaluation ticker and for SPY on each trading day using the same lookback window the analyst stage will request; SPY history is required by the portfolio manager's self-reflection and benchmark-relative realized-return calculations. Wrote 244 persistent `get_stock_data` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, SPY 61.
- [x] (2026-06-17) Implemented and populated dataset building for `get_indicators`: records all allowed indicators from `src/trading_agents/tools/market_data.py` for each configured ticker and trading day using the analyst-stage lookback window. Wrote 183 persistent `get_indicators` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero SPY indicator rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison matched for `AMZN` on `2024-02-27` with 12 indicators.
- [x] (2026-07-17 14:36Z) Corrected live and replay indicator warm-up: calculations now use five years of pre-window OHLCV and trim output back to the requested seven-day range. The builder downloads once per ticker, requires at least 200 observations through the first displayed date, renders all replacements before an atomic write, and regenerated all 183 indicator payloads. The audit found zero blank indicator cells, boundary errors, row-count errors, or fresh-render mismatches; focused validation reports 74 passed and the full suite reports 192 passed.
- [x] (2026-06-17 13:03Z) Implemented and populated shared dataset building for `get_news`: records ticker-news text through the Exa historical source layer with the same markdown/no-news/error contract as the live Yahoo-backed tool. The builder uses a doubled news limit (`settings.news.ticker_limit * 2`, currently 40) for buffer coverage, writes ticker rows only, and shares the same implementation with Plan B. Wrote 183 persistent `get_news` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero error payloads and zero no-news fallback rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AMZN on `2024-03-05`; the evaluation-backed `get_news` tool matched the DuckDB payload exactly and returned 39 articles for `2024-02-27..2024-03-05`.
- [x] (2026-07-18) Repaired the audited unrelated-content contamination in canonical
  `get_news` payloads without calling Exa. Atomically removed exactly 91 complete article
  blocks from 28 ticker/date rows while preserving the heading, article order, all other
  article bytes, and all 1,863 non-target tool-output rows. The 29th audited row, AAPL on
  `2024-03-25`, remained unchanged because it had no clearly unrelated article. All 183
  `get_news` rows remain; their ordered content hashes to
  `530cb77282ff60ec32ede791abd44bbad9647e6fe527713fbe4eb79137ad7c32`,
  the DuckDB hashes to
  `0012b679ace8198dbef5cebf4c20d012f0cce7462f35936d97ab6ccdc8c703cd`,
  and `tests/test_eval_dataset.py` reported 11 passed. Future-dated, post-trade,
  competitor, partner, regulatory, and broadly relevant articles were intentionally
  retained unless they were one of the audited unrelated blocks.
- [x] (2026-07-18) Repaired the audited post-trade-publication contamination in
  canonical `get_news` payloads without calling Exa. Using publication date only,
  atomically removed exactly ten complete article blocks from ten ticker/date rows and
  verified all 1,881 non-target tool-output rows remained byte-identical. All 183
  `get_news` rows remain; their ordered content hashes to
  `87eade356edc610e0ccc74f8138e7e58e7c4eebf13e6519ce5a7bba708608797`,
  the DuckDB hashes to
  `ed20626ea0ffb3f777aa26e09845c34ec693ad81fac27a23faa451ba8616e92b`,
  and `tests/test_eval_dataset.py` reported 11 passed. Pre-trade publications that
  discuss future events or whose stored summaries contain later injected page content
  were intentionally retained for separate review.
- [x] (2026-06-17) Implemented and populated shared dataset building for `get_global_news`: records one Exa historical global-market-news payload per trading day, stores it under each evaluated ticker key for existing dataset-backed tool replay, and uses a doubled global-news limit (`settings.news.global_limit * 2`, currently 20). Wrote 183 persistent `get_global_news` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61, with zero error payloads and zero no-news fallback rows. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_exa_sources.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-03-21`; the evaluation-backed `get_global_news` tool matched the DuckDB payload exactly and returned the shared global payload for all ticker keys on that date.
- [x] (2026-07-17 07:40Z) Implemented canonical dataset building for `fetch_reddit_posts`: validates all retained Arctic Shift pages and required fields, requires every configured ticker/subreddit stream and full replay-window coverage, deduplicates by ticker/post ID, and renders rich date/score/comment/title/body payloads without network calls. Extended raw Reddit rows to retain source IDs and engagement counts. Ingested 1,051 unique posts and 183 tool payloads into `data/eval_dataset.duckdb` (61 each for AAPL, GOOGL, and AMZN). Focused tests reported 37 passed.
- [x] (2026-07-17 13:30Z) Aligned live and replay Reddit output with upstream recent-post semantics: removed score/comment quality gates, retained the configurable five-post-per-subreddit default, added upstream named empty-subreddit and all-empty messages, and atomically regenerated all 183 Reddit payloads from the local Arctic Shift archive. All 183 prior payloads changed; all now contain recent posts, 26 named partial-empty blocks remain, and zero old no-data or blank-subreddit blocks remain. The full suite reports 190 passed.
- [x] (2026-07-17 08:02Z) Implemented canonical dataset building for `fetch_stocktwits_messages`: validates all 21,165 retained pagination pages, their numeric filename sequence, symbol/cursor/message schemas, decreasing cursor bounds, page chronology, duplicate consistency, and full replay-window coverage before writes. Messages are chronologically normalized and rendered in the live sentiment format without StockTwits or Exa calls. Populated 183 payloads in `data/eval_dataset.duckdb` (61 per ticker); every payload contains the configured 30 messages. Focused validation reported 69 passed.
- [x] Implement dataset building for `get_fundamentals`: record best-effort fundamentals text for each ticker and trading day.
- [x] (2026-07-17 14:58Z) Corrected AMZN dividend-yield reporting without a ticker-specific exception. The formatter now prefers Yahoo's percentage-point `dividendYield` and falls back to `trailingAnnualDividendYield * 100`; Yahoo's explicit trailing zero therefore renders as `Dividend yield: 0` instead of a missing field. Atomically replaced only the 61 AMZN `get_fundamentals` rows. All 61 contain the zero value, none retain the missing warning, the other 1,830 tool outputs retain SHA-256 `6b7d21158488f67a6927c943969e50ac3a848a5c8362e28b262a11b62c3121e6`, focused validation reports 76 passed, and the full suite reports 194 passed.
- [x] (2026-07-17 16:16Z) Replaced all 183 `get_fundamentals` replay payloads with SEC-backed point-in-time fundamentals. The builder loads `SEC_UA` from `.env`, archives SEC submissions/companyfacts and the required 10-K/10-Q filing packages under `data/raw-backtest/SEC`, validates the manifest before reuse, selects only filings strictly before each replay date, and uses only prior closes for market-derived values. The refreshed DuckDB has 61 rows each for AAPL, GOOGL, and AMZN, 183 distinct fundamentals payloads, zero current-snapshot markers, and zero point-in-time audit issues. The six source filings are AAPL `0000320193-23-000106`/`0000320193-24-000006`, GOOGL `0001652044-23-000094`/`0001652044-24-000022`, and AMZN `0001018724-23-000018`/`0001018724-24-000008`. The fundamentals rows now hash to `3fe1dde177879fba3950746441151889f038ddc6885cb91a469a4ddcc7f69d72`; all non-fundamentals rows hash to `745b4ad85b5b62b2b4b27c864d958c8e7d050641da59b7d42dcb51278a092d1b`; the full DuckDB hashes to `0a0d5408e8456dc880d49f9ea392eb71d3fc507092c631d1470e8d79460b8b25`. Focused validation reported 41 passed, and the full suite reported 201 passed.
- [x] (2026-06-18 14:16Z) Implemented and populated shared dataset building for `get_balance_sheet`: records the yfinance latest balance-sheet statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_balance_sheet` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-03-08`; the evaluation-backed `get_balance_sheet` tool matched the live tool exactly and AAPL had one distinct payload across all 61 replay dates.
- [x] (2026-07-18 07:19Z) Replaced all 183 `get_balance_sheet` replay payloads with SEC-backed point-in-time statements. The renderer selects the latest 10-K/10-Q filed strictly before each trade date, emits the two latest instant USD periods disclosed under that filing's accession, validates required accounting totals, and derives AMZN total liabilities as assets minus equity where the standalone fact is unavailable. GOOGL switches filings on `2024-02-01`; AAPL and AMZN switch on `2024-02-05`. The audit found 61 rows per ticker, zero legacy Yahoo markers, zero 2024/2025 future periods, and zero filing-date/report-period violations. Balance-sheet rows hash to `0cba5d92654a13278e454dd7dc0db1c8eedca1cd90deffa54b75babcfe71ea04`; the other 1,708 tool outputs remained unchanged at `a15dd31c6d2b85a4140677100d7c332dee6480d0323b2ce63f238cf7fa948c61`; the DuckDB hashes to `729976be58a068d3c48445f5826883eeb48d74d629492943aad1b41b39f96aca`. Focused validation reported 86 passed and the full suite reported 204 passed.
- [x] (2026-06-18 14:24Z) Implemented and populated shared dataset building for `get_cashflow`: records the yfinance latest cash flow statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_cashflow` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AAPL on `2024-01-12`; the evaluation-backed `get_cashflow` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [x] (2026-07-18 07:45Z) Replaced all 183 `get_cashflow` replay payloads with SEC-backed point-in-time statements. The renderer selects annual comparative periods for 10-Ks and fiscal-year-to-date/prior-year comparative periods for 10-Qs, excludes quarter-only and trailing-twelve-month facts, derives free cash flow, and reconciles operating, investing, financing, and exchange-rate effects to the reported change in cash. GOOGL switches filings on `2024-02-01`; AAPL and AMZN switch on `2024-02-05`. The audit found 61 rows per ticker, zero legacy Yahoo markers, zero future periods, zero filing-date/report-period/accession violations, and zero reconciliation failures. Cash-flow rows hash to `b4c92f1920a306ac0cef8ccee655e23a328020b649060bbdf698eefbbf2b0527`; the other 1,708 tool outputs remained unchanged at `d4a82b721b62b3ef7c73eb000a381e5c65efc9b9759fac05e6a5a13434cb6299`; the DuckDB hashes to `f2b788a5c010a628c28cc5d6379b94c1462223b76a0ade38f3ab0e47186eeecf`. Focused validation reported 90 passed and the full suite reported 208 passed.
- [x] (2026-06-18 14:30Z) Implemented and populated shared dataset building for `get_income_statement`: records the yfinance latest income statement once per ticker and writes the same best-effort statement text for each trading day because the live tool is not date-parameterized. Wrote 183 persistent `get_income_statement` rows to `data/eval_dataset.duckdb`: AAPL 61, GOOGL 61, AMZN 61. Focused validation passed with `uv run pytest tests/test_eval_build_dataset.py tests/test_eval_dataset.py tests/test_eval_backtest.py tests/test_trading_tools.py`. Random replay comparison used AMZN on `2024-02-28`; the evaluation-backed `get_income_statement` tool matched the live tool exactly and each ticker had one distinct payload across all 61 replay dates.
- [x] (2026-07-18 08:03Z) Replaced all 183 `get_income_statement` replay payloads with SEC-backed point-in-time statements. The renderer selects three annual periods for 10-Ks and current/prior-year quarterly periods for 10-Qs, excluding year-to-date and trailing-twelve-month facts, and validates gross profit, pretax/tax/net-income reconciliation, and diluted-EPS consistency where the source facts permit. GOOGL switches filings on `2024-02-01`; AAPL and AMZN switch on `2024-02-05`. The audit found 61 rows per ticker, zero legacy Yahoo markers, zero future periods, zero filing-date/report-period/accession violations, and zero arithmetic failures. Income-statement rows hash to `9b82ab9bb1b6b0b811fdf763a54b5e63cef4d70b678bc2f1596c3035c5af5c9a`; the other 1,708 tool outputs remained unchanged at `bd02e97fc80e3cd9198cd36195486f760b8d1a22022e24010cfdcbc268a10260`; the DuckDB hashes to `aecc34cdfbba6dac5e5c57784d0afc218415666d72d517941749c4edddab0289`. Focused validation reported 96 passed and the full suite reported 214 passed.
- [x] (2026-07-16) Historical Reddit-source gate opened for the configured 2024-Q1 evaluation: Arctic Shift API responses were collected and retained under `data/raw-backtest/arctic-shift/` (210 JSON pages: AAPL 62, GOOGL 84, AMZN 64). The remaining work is offline archive validation and dataset ingestion, not a live-source probe or replacement-period scan.
- [x] (2026-07-16) Historical StockTwits-source gate opened for the configured 2024-Q1 evaluation: retained pagination responses under `data/raw-backtest/stocktwits/` reach before the 2023-12-18 two-week-lookback cutoff for every ticker (21,165 JSON pages: AAPL 10,983, GOOGL 3,562, AMZN 6,620). The remaining work is offline archive validation and dataset ingestion, not live StockTwits pagination.
- [x] (2026-06-11) Created `src/trading_agents/evaluation/eval_tools.py` (dataset-backed `DatasetBackedTool` + `build_dataset_tools`). Remaining: the analyst-crew tool-injection seam.
- [x] (2026-06-11) Created `src/trading_agents/evaluation/backtest.py` (`simulate_position` + `cumulative_return`).
- [ ] (pending) Create `src/trading_agents/evaluation/run_eval.py` and the `run-eval` entry point.
- [x] (2026-06-11) Added unit tests `tests/test_eval_backtest.py` (10) and `tests/test_eval_dataset.py` (7); all pass, full suite 113 passed with no regressions.
- [ ] (pending) Build the committed dataset `data/eval_dataset.duckdb` and run a smoke evaluation.
- [x] (2026-07-17) Audited all 1,891 prepared tool-output keys, 364 price rows, and
  1,051 raw Reddit rows for missing records, no-data fallbacks, stored HTTP/API errors,
  time bounds, malformed payloads, and suspicious future content. Key coverage is
  complete and no stored API/runtime errors were found, but the dataset is not ready:
  confirmed future/unrelated ticker and global news contaminates multiple rows;
  and 133 unused GOOGL raw Reddit posts are dated in 2025-12-19..2026-02-13.
- [ ] (pending) Resolve the remaining dataset-readiness audit findings before the smoke evaluation:
  repair or exclude remaining future or later-injected ticker-news and contaminated global-news
  blocks, and remove future raw Reddit rows from the canonical artifact. The audited
  unrelated and post-trade-published ticker-news blocks, Reddit replay-output, indicator
  warm-up, fundamentals, and all financial-statement findings are resolved; the other
  news and future raw-row cleanup remains separate.
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
- Observation: The checked-in StockTwits pagination archive has sufficient historical
  coverage for the Plan 07 two-week lookback for every evaluation ticker.
  Evidence: Commit `a33bee20c7f866df994e8ca70c310cc9cd992ca1` records a successful
  Stage 2 scan to the 2023-12-18 cutoff. Terminal pages reached 2023-12-17 for AAPL,
  GOOGL, and AMZN; the archive contains 21,165 JSON pages (AAPL 10,983, GOOGL 3,562,
  AMZN 6,620). The scanner's numeric filename-ordering fix handles the AAPL archive's
  five-digit sequence numbers.
- Observation (2026-07-17): StockTwits pagination is chronologically monotonic at the
  page level, but individual provider pages are not guaranteed to order every message.
  Evidence: strict validation found an internal timestamp inversion in
  `AMZN-0974.json`; all 21,165 pages still had decreasing cursor bounds and non-increasing
  newest-page timestamps. The loader now sorts messages within pages before global
  deduplication and rendering rather than rejecting a valid provider response.
- Observation (2026-07-17): The retained StockTwits archive is complete for the
  canonical replay window and contains no duplicate message IDs.
  Evidence: validation accepted contiguous numeric sequences AAPL `1..10983`, GOOGL
  `1..3562`, and AMZN `1..6620`, each spanning 2023-12-17 through at least 2026-07-13.
  The bounded canonical render retained 43,743 AAPL, 9,090 GOOGL, and 15,926 AMZN
  messages from the required lookback/replay range and produced 183 full payloads.
- Observation (2026-07-17): A post-build audit found complete key coverage but material
  point-in-time and content-quality defects in `data/eval_dataset.duckdb`.
  Evidence: all 1,891 expected tool keys and all 364 expected positive price rows are
  present, with no stored HTTP/API/runtime errors. The six GOOGL Reddit payloads originally
  appeared as no-data fallbacks, and all 183 indicator payloads originally had blank
  first-row `boll_lb` and `boll_ub`; all 183 current-fundamentals rows and all 549
  financial-statement rows originally used
  snapshots unavailable on their 2024-Q1 trade dates; at least 29 ticker-news rows and
  18 replicated global-news rows contain confirmed future/unrelated material; and the
  raw Reddit table retains 133 GOOGL posts from late 2025/early 2026. The Reddit payload
  finding was resolved on 2026-07-17 by removing obsolete engagement filtering and
  rebuilding every Reddit output. The indicator finding was resolved the same day with
  five years of calculation warm-up and a complete replay refresh. The fundamentals
  finding was resolved the same day with SEC-backed point-in-time payloads. The balance-sheet
  balance-sheet, cash-flow, and income-statement findings were resolved on 2026-07-18
  with SEC-backed statements; news and future raw-Reddit findings still block readiness.
- Observation: The original TradingAgents repository works around Reddit JSON
  blocking by using Reddit RSS/Atom search first.
  Evidence: `https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/dataflows/reddit.py`
  documents that `/search.json` is WAF-blocked for public clients and fetches
  `/search.rss` by default. A local probe on 2026-06-15 for
  `https://www.reddit.com/r/wallstreetbets/search.rss?q=AAPL&restrict_sr=on&sort=new&t=week&limit=5`
  returned HTTP 200 with two Atom entries dated 2026-06-10 and 2026-06-09. This is
  useful for fixing live Reddit fetching, but it still does not provide exact
  historical date-range access for the 2024-Q1 backtest.
- Observation: Arctic Shift preserves the post-engagement fields needed to reproduce
  the rich live `fetch_reddit_posts()` presentation, unlike the RSS archive path.
  Evidence: Arctic Shift post responses include `score` and `num_comments` together
  with timestamps, subreddit, title, and selftext. The live formatter in
  `src/trading_agents/tools/sentiment.py` presents post date, score, comment count,
  title, and body excerpt. Therefore the evaluation can render format-equivalent
  historical payloads from Arctic Shift without substituting Reddit RSS.
- Observation (2026-07-17): The retained Arctic Shift archive passes offline schema,
  stream, and replay-window coverage validation and contains 1,051 unique ticker/post
  pairs after ID deduplication.
  Evidence: the loader reported 62 AAPL pages with 475 posts, 84 GOOGL pages with 284
  posts, and 64 AMZN pages with 292 posts. It validated the required 2023-12-26 through
  2024-03-28 span for all three tickers and wrote 61 payload rows per ticker. Initial
  engagement filtering produced 177 rich rows and 6 misleading empty rows; the later
  recency-only rebuild produces rich recent-post content in all 183 rows. The full
  repository suite reported 190 passed after that rebuild.
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
  dataset and source it from the checked-in Arctic Shift archive for the
  `fetch_reddit_posts` builder step.
  Rationale: The README evaluation lists Reddit among the analyst data sources, and the
  user confirmed that missing Reddit should not be silently accepted. The historical
  corpus is now present locally, which makes the build reproducible and avoids the
  rate-limit and coverage uncertainty of a live source. The builder must validate the
  archived pages and coverage before writing payloads; other builders remain independent.
  Date/Author: 2026-07-16 / Codex (confirmed with the user)

- Decision: Treat `data/raw-backtest/arctic-shift/` as an immutable, auditable input
  artifact rather than fetching Reddit during dataset construction.
  Rationale: Its 210 retained JSON pages cover the three evaluation tickers and remove
  the need for a live availability/status probe. Archive parsing still distinguishes
  malformed pages, missing required fields, and insufficient date coverage from a valid
  empty rendered window; it must fail before DuckDB writes for the first three cases.
  Date/Author: 2026-07-16 / Codex

- Decision: Use Arctic Shift exclusively—not Reddit RSS—to prepare Plan 07 Reddit
  dataset payloads, and render its retained posts in the live `fetch_reddit_posts()`
  rich format.
  Rationale: Arctic Shift supplies `score` and `num_comments` as well as the textual
  fields, enabling the historical payload to include the same engagement metadata as
  the live sentiment tool. RSS remains relevant only to the separate live-fetch repair;
  it is not a dataset-preparation fallback for this evaluation.
  Date/Author: 2026-07-16 / Codex

- Decision (superseded): Apply the live Reddit tool's strict quality gates when rendering
  Arctic Shift replay payloads and retain the unfiltered archive rows for auditability.
  Rationale: `fetch_reddit_posts()` only presents posts whose score and comment count
  exceed the configured minima. Matching that behavior keeps evaluation prompts
  format- and quality-equivalent, while storing every valid deduplicated source post
  preserves the evidence needed to inspect or rerender the dataset later.
  Date/Author: 2026-07-17 / Codex

- Decision: Select recent Reddit posts without score/comment thresholds, cap each
  subreddit with the configurable `reddit_limit_per_sub` setting (default 5), and use
  upstream empty-result messages.
  Rationale: Current upstream `fetch_reddit_posts()` presents the newest posts returned by
  the seven-day search and does not discard low-engagement results. The former strict
  `AND` gate mislabeled six GOOGL windows as having no data despite archived posts. Shared
  live/replay semantics and an atomic full-payload rebuild prevent that drift from
  recurring while Arctic Shift still supplies score/comment metadata for display.
  Date/Author: 2026-07-17 / Codex (confirmed with the user)

- Decision: Calculate every technical indicator with five years of pre-window OHLCV,
  then trim the rendered CSV to the requested analyst lookback.
  Rationale: `stockstats` uses a 20-session rolling sample standard deviation for
  Bollinger bands, so calculating directly on the display slice leaves the first bands
  undefined. A 200-session minimum would fully cover fixed windows, but EMA, MACD, RSI,
  and ATR are recursive and benefit from a longer initialization period. Five years
  matches upstream's history-depth policy, does not expose warm-up rows or future prices,
  and was selected by the user over shorter warm-up alternatives.
  Date/Author: 2026-07-17 / Codex (confirmed with the user)

- Decision: Treat `data/raw-backtest/stocktwits/` as an immutable, auditable input
  artifact rather than paginating StockTwits during dataset construction.
  Rationale: The completed Stage 2 scanner has already demonstrated coverage through
  the required two-week pre-window cutoff for AAPL, GOOGL, and AMZN. Offline parsing
  makes replay reproducible and eliminates API rate-limit and cursor-resumption risk;
  the builder must still reject malformed pages, missing fields, or insufficient
  selected ticker/date coverage before writing DuckDB rows.
  Date/Author: 2026-07-16 / Codex

- Decision: Validate StockTwits pagination order from numeric filenames, decreasing
  cursor bounds, and non-increasing page-level newest timestamps, then explicitly sort
  messages within each page.
  Rationale: numeric sequencing and cursor/page bounds detect missing, reordered, or
  ambiguous archive pages. StockTwits does not guarantee strict timestamp order inside a
  response page, as demonstrated by `AMZN-0974.json`, so rejecting internal inversions
  would discard valid data; deterministic sorting provides the required chronological
  replay order.
  Date/Author: 2026-07-17 / Codex

- Decision: Track the RSS-first live Reddit fix in Plan 01, but keep Plan 07's
  historical Reddit requirement separate.
  Rationale: RSS-first fetching should repair the current live `fetch_reddit_posts`
  behavior and can make recent Reddit diagnostics more trustworthy. It does not
  replace the Plan 07 requirement for historical, date-bounded Reddit data, so the
  evaluation builder must still use a date-bounded historical corpus. Arctic Shift is
  now that corpus for Plan 07; this does not alter the live RSS implementation.
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
news/social source helpers that were initially planned for the dataset builder:

- `src/trading_agents/evaluation/exa_sources.py` loads `.env`, requires `EXA_API_KEY`,
  constructs an `exa_py.Exa` client, and exposes helpers for ticker news, global market
  news, Reddit, and StockTwits.
- The helpers use Exa published-date filters, render news via the existing
  `_format_news_block` style, and return the existing sentiment fallback strings when no
  historical social results are found.
- Tests `tests/test_eval_exa_sources.py` (6) pass with mocked Exa calls; the focused
  evaluation suite is now **23 passed** across Exa sources, dataset, and backtest.

What remains after this milestone: create `build_dataset.py` and the
`build-eval-dataset` entry point. The later completed Reddit and StockTwits archive
collection supersedes the Exa social helpers for Plan 07 ingestion; Exa remains the
historical source for news.

Milestone 3 — Arctic Shift archive acquisition (2026-07-16). The former live Reddit
availability/status gate is open: 210 historical Arctic Shift response pages were
collected under `data/raw-backtest/arctic-shift/` (AAPL 62, GOOGL 84, AMZN 64). The
remaining `fetch_reddit_posts` builder work is to validate, parse, deduplicate, and
render this local corpus before writing Reddit payloads. This does not alter live
Reddit/RSS behavior or block non-Reddit builders.

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

At this milestone, all analyst tool-output writers were still pending; the later Arctic
Shift archive acquisition replaces the planned live Reddit availability check.

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

Remaining builder work: validate and ingest the local Arctic Shift corpus before Reddit
payload writes, plus the nine remaining analyst tool-output writers. Non-Reddit writers
should be implemented, tested, collected into DuckDB, and summarized independently of
Reddit archive ingestion.

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

Milestone 9 — Canonical Arctic Shift Reddit ingestion (2026-07-17). Replaced the
canonical builder's live RSS path with an offline archive loader while retaining RSS for
Plan B. The loader validates JSON structure, filenames, required rich post fields,
ticker/subreddit stream presence, duplicate consistency, and the requested lookback/date
span before writing sentiment rows. Raw DuckDB rows now retain Arctic Shift post IDs,
scores, and comment counts. The completed ingestion wrote 1,051 unique raw rows and 183
`fetch_reddit_posts` payloads to `data/eval_dataset.duckdb`; focused builder and dataset
tests reported 37 passed, the broader evaluation/tool suite reported 64 passed, and the
full repository suite reported 181 passed. Both canonical social-source archives are now
validated and populated.

Milestone 10 — Canonical StockTwits archive ingestion (2026-07-17). Replaced the
lenient per-ticker reader with a structured offline archive loader that validates page
filenames numerically, requires contiguous sequences, checks symbol/cursor/message
schemas, verifies decreasing cursor and page-time bounds, rejects conflicting duplicate
IDs, and proves the requested historical span before writing outputs. The loader retains
only messages relevant to the selected replay window in memory, then globally sorts them
for deterministic rendering. The completed ingestion validated 10,983 AAPL, 3,562 GOOGL,
and 6,620 AMZN pages and wrote 183 full `fetch_stocktwits_messages` payloads to
`data/eval_dataset.duckdb`. Focused builder/dataset/backtest/tool validation reported 69
passed, and the full repository suite reported 186 passed.

Milestone 11 — Reddit recent-post alignment and full replay refresh (2026-07-17).
Removed the obsolete score/comment thresholds from settings, live fetching, the
canonical archive renderer, and the legacy Arctic Shift patch path. Both live and
historical formatting now name an empty subreddit and use the upstream aggregate message
when every subreddit is empty. `EvalDataset.put_tool_outputs()` provides an atomic batch
upsert, so the canonical builder renders every Reddit payload before replacing stored
rows. The offline refresh rewrote all 183 Reddit outputs (61 per ticker) from 1,051 raw
posts; zero fresh-render mismatches, old no-data fallbacks, or blank subreddit blocks
remain. The 1,708 unrelated tool outputs retained SHA-256
`ffed0472b518d639728e1c682ad7c244c981f269cb4c949b4b7f5cbdb39afbf1` before and after,
focused validation reported 80 passed, and the full suite reported 190 passed.

Milestone 12 — Five-year indicator warm-up and full replay refresh (2026-07-17).
Refactored `get_indicators_text()` into shared history acquisition and rendering steps.
Live calls fetch five years before the requested start; the renderer calculates on that
history and emits only `[start_date, end_date)`. The dataset builder reuses one OHLCV
download per ticker for all 61 dates, validates at least 200 observations through the
first displayed date, renders all 183 rows before an atomic batch upsert, and rejects
failed payloads before writing. All 183 stored indicator payloads changed. The audit
reported zero blank requested-indicator cells, date-boundary violations, row-count
errors, or fresh-render mismatches. The 1,708 unrelated tool outputs retained SHA-256
`fc7d6d954df69d71e924cab384d1929744d07693c33479fb117574230a03f83a` before and after;
focused validation reported 74 passed and the full suite reported 192 passed.

Milestone 13 — AMZN zero-dividend normalization (2026-07-17). Yahoo omits AMZN's
primary `dividendYield` while returning an explicit zero in
`trailingAnnualDividendYield`. The live fundamentals formatter now prefers the primary
percentage-point value and otherwise converts the trailing ratio to percentage points,
so a confirmed zero is not classified as missing. An atomic targeted refresh replaced
all 61 AMZN fundamentals payloads and left the other 1,830 tool outputs unchanged at
SHA-256 `6b7d21158488f67a6927c943969e50ac3a848a5c8362e28b262a11b62c3121e6`.
Focused validation reported 76 passed and the full suite reported 194 passed. This
semantic correction does not resolve the separate point-in-time snapshot finding.

Milestone 14 — SEC point-in-time fundamentals (2026-07-17). The `get_fundamentals`
dataset builder now uses a local SEC archive instead of Yahoo's latest `.info`
snapshot. `ensure_sec_archive()` loads `SEC_UA` from `.env`, downloads SEC ticker,
submissions, companyfacts, and required 10-K/10-Q filing-package files into
`data/raw-backtest/SEC`, and validates a SHA-256/size manifest before archive reuse.
`render_point_in_time_fundamentals()` selects only the latest filing with
`filing_date < trade_date`, uses only the latest stored close before the trade date,
and omits fields that cannot be reconstructed safely from the archive. The refresh
atomically replaced all 183 fundamentals rows. The audit found 61 rows each for AAPL,
GOOGL, and AMZN, 183 distinct payloads, zero stale Yahoo snapshot markers, and zero
source-date violations. The SEC archive has 49 manifest entries and 50 files including
the manifest. Focused validation reported 41 passed; the full suite reported
201 passed.

Milestone 15 — SEC point-in-time balance sheets (2026-07-18). The
`get_balance_sheet` dataset builder now reuses the validated local SEC archive and
renders only facts disclosed by the latest 10-K/10-Q filed strictly before each replay
date. Each payload identifies the filing and accession, includes up to two comparative
instant USD periods from that accession, validates total assets against liabilities and
equity, and labels AMZN liabilities derived from assets minus equity where SEC Company
Facts omits the standalone total. The atomic refresh replaced all 183 balance-sheet
rows. The audit found 61 rows per ticker, zero legacy Yahoo markers, zero future fiscal
periods, and zero filing-date or report-period violations. Focused validation reported
86 passed; the full suite reported 204 passed.

Milestone 16 — SEC point-in-time cash-flow statements (2026-07-18). The
`get_cashflow` dataset builder now reuses the validated local SEC archive and renders
only duration facts disclosed by the latest 10-K/10-Q filed strictly before each replay
date. Ten-K payloads contain three annual periods; 10-Q payloads contain the current
fiscal-year-to-date period and prior-year comparison, excluding quarter-only and
trailing-twelve-month duplicates. Each payload derives free cash flow and reconciles
operating, investing, financing, and exchange-rate effects to the reported change in
cash before the atomic write. The refresh replaced all 183 cash-flow rows. The audit
found 61 rows per ticker, zero legacy Yahoo markers, zero future periods, and zero
filing-date, accession, period, or reconciliation violations. Focused validation
reported 90 passed; the full suite reported 208 passed.

Milestone 17 — SEC point-in-time income statements (2026-07-18). The
`get_income_statement` dataset builder now reuses the validated local SEC archive and
renders only duration facts disclosed by the latest 10-K/10-Q filed strictly before
each replay date. Ten-K payloads contain three annual periods; 10-Q payloads contain
the current fiscal quarter and prior-year comparison, excluding year-to-date and
trailing-twelve-month duplicates. Each payload validates reported gross profit,
pretax/tax/net-income arithmetic with a narrow rounding tolerance, and diluted EPS
against diluted shares where those facts are available. The atomic refresh replaced
all 183 income-statement rows and retired the final current-snapshot builder path. The
audit found 61 rows per ticker, zero legacy Yahoo markers, zero future periods, and
zero filing-date, accession, period, or arithmetic violations. Focused validation
reported 96 passed; the full suite reported 214 passed.


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

- `get_stock_data`, `get_indicators` in `src/trading_agents/tools/market_data.py` (the underlying functions are `get_stock_data_text(ticker, start_date, end_date)` and `get_indicators_text(ticker, start_date, end_date, indicators)`). Stock data downloads the requested range; indicators download five years of pre-window OHLCV, calculate on the full history, and render only the requested range.
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

- Prices and indicators are fully available historically through yfinance. Stock-price payloads use the requested range. Indicator payloads require five years of pre-window OHLCV so long-window and recursive calculations are initialized before the first displayed row; the builder downloads one reusable history per ticker and renders only the analyst lookback window for each trade date.
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` are now built from an archived SEC EDGAR source under `data/raw-backtest/SEC`, with filing dates strictly before each replay date and prior-close dates also enforced for market-derived fundamentals. All four fundamentals/financial-statement replay sources are point-in-time safe for the evaluation window.
- News (`get_news`, `get_global_news`) is **not** historically queryable through the
  existing tools, so the builder sources it from **Exa** with published-date filters.
  Reddit and StockTwits are read from their checked-in historical archives instead.
- Reddit is a required source for this evaluation, not an optional enhancement. The
  Arctic Shift gate is open: 210 raw response pages for AAPL, GOOGL, and AMZN are stored
  under `data/raw-backtest/arctic-shift/`. Dataset construction is therefore offline for
  Reddit and must validate the recorded corpus rather than probing a provider. Other
  builders remain independent of Reddit archive ingestion.
- StockTwits is likewise a required source. Its completed two-stage pagination archive
  contains 21,165 pages under `data/raw-backtest/stocktwits/` and reaches before
  2023-12-18 for AAPL, GOOGL, and AMZN. Dataset construction must validate this local
  corpus rather than make a StockTwits or Exa request.


## Plan of Work

Most evaluation code lives in `src/trading_agents/evaluation/`, with integration edits
in settings, the analyst crew, script entry points, the README, and the end-to-end-flow
plan. Evaluation routing remains inactive unless `settings.evaluation.enabled` is true.
Two data-quality fixes intentionally also affect live tool behavior: Reddit now uses
recent-post selection and upstream-compatible empty messages, and indicators calculate
against five years of pre-window history before trimming to the requested output range.

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
`fetch_global_news_via_exa(curr_date, look_back_days, limit)`. Only the builder imports
this module. Reddit and StockTwits archive parsing belongs in the dataset builder or
dedicated local archive helpers; neither requires `EXA_API_KEY`.

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
from `get_stock_data_text` using the analyst display window. For indicators, download
one five-year-warmed OHLCV superset per ticker, require at least 200 observations through
the first displayed date, calculate every payload from that shared history, and trim
each payload to `start = trade_date - lookback_days`, `end = trade_date`. Render and
validate all indicator payloads before one atomic batch upsert. The remaining records
come from the Exa news and global-news blocks, the StockTwits archive-derived block, the
Arctic Shift archive-derived Reddit block, and
best-effort fundamentals/statement text. Use `EvalDataset.put_prices()` and
`put_tool_output()` so the build is idempotent. Support `--tickers` and `--limit-days`.

The Arctic Shift archive-validation gate is local and belongs only to the
`fetch_reddit_posts` builder step. Before any Reddit `tool_outputs` writes, parse all
selected archive pages, enforce the expected JSON schema and timestamps, deduplicate by
Reddit post ID, require `score` and `num_comments`, and confirm the selected ticker/date
windows can be rendered from the archive. Render the same date/score/comment-count/title/
body-excerpt shape as live `fetch_reddit_posts()`; do not use Reddit RSS for dataset
preparation. A malformed page, missing field, or insufficient corpus coverage is a hard
failure; a valid zero-post lookback renders the normal no-data text. This local gate must
not prevent the other nine analyst tools from being implemented or collected.

The StockTwits archive-validation gate is likewise local and belongs only to the
`fetch_stocktwits_messages` builder step. Before any StockTwits `tool_outputs` writes,
parse all selected pagination pages, enforce the expected message and cursor schema,
sort files by numeric sequence (not lexical filename order), deduplicate messages, and
confirm the selected ticker/date windows are covered through the required pre-window
lookback. A malformed page, missing field, non-monotonic/ambiguous page sequence, or
insufficient coverage is a hard failure; a valid zero-message lookback renders the
normal no-data text. This local gate must not prevent the other nine analyst tools from
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
requests exceeded Reddit's tight shared budget. That operational constraint no longer
applies to Plan 07 ingestion because it reads the local Arctic Shift archive. Preserve
the archive unchanged, make no network request, and distinguish a valid empty lookback
from malformed or incomplete archive input.

Apply the same offline principle to StockTwits: preserve the pagination archive
unchanged, make no network request, order its mixed-width sequence filenames numerically,
and distinguish a valid empty lookback from malformed or incomplete archive input.

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

4. Before writing social-sentiment payloads, validate the checked-in Arctic Shift and
   StockTwits archives (no network):

       uv run build-eval-dataset --tickers AAPL --limit-days 3

   Expected: each social builder reports archive page/message counts, selected ticker
   coverage, duplicate count, and rendered ticker-day rows. It must fail before its
   writes if a selected page is malformed, a required field is absent, or the requested
   lookback cannot be covered. It must not call Reddit, StockTwits, Exa, or Arctic Shift.

5. Build each small dataset slice after its code and focused tests pass:

       uv run build-eval-dataset --tickers AAPL --limit-days 3

   Expected: collect the implemented source slice and print a summary naming the DuckDB
   file, tool name, tickers, covered trading days, row count, and warnings. The Reddit
   builders first validate their local archives; no provider availability gate or live
   social-data request remains.

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
  passes after the builder is added. The builder tests must mock Exa/yfinance as needed
  and use archive fixtures to assert schema validation, ID/message deduplication,
  numeric StockTwits filename ordering, historical lookback boundaries, rich-payload
  rendering, and no Reddit/StockTwits/Exa/Arctic Shift network call during social
  ingestion.
- The Reddit and StockTwits archive builders reject malformed pages, missing required
  fields, and insufficient requested ticker/date coverage before they create or update
  their `tool_outputs` rows. A partially empty Reddit result names each empty subreddit;
  an all-empty result uses the upstream aggregate seven-day message.
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

The local Arctic Shift and StockTwits archive-validation gates run before writing their
respective sentiment `tool_outputs` rows. If either selected archive is malformed or
lacks required selected coverage, that builder fails with a clear report and leaves
existing rows intact. The archives themselves are never rewritten by the builder.
Missing or degraded archive input must not block
collection for prices, `get_stock_data`, `get_indicators`, `get_news`,
`get_global_news`, `fetch_stocktwits_messages`, or fundamentals/statement tools.

After validation passes, the dataset build uses `INSERT OR REPLACE`, so it can be run
repeatedly and partially (via `--tickers`/`--limit-days`) without duplicating rows.
Reddit payloads are rendered in memory and batch-upserted in one transaction, preventing
a partial Reddit refresh; rerunning refreshes existing rows. The evaluation run writes only under `output/eval/`
and uses an isolated lessons directory there, so it never disturbs ordinary
`output/<ticker>_<date>/` run artifacts; delete `output/eval/` to start a clean
evaluation. If the build is interrupted after the gate passes, rerun it — completed
(ticker, day) rows are simply overwritten. If a needed `tool_outputs` row is missing at
evaluation time, `EvalDataset.tool_output` raises a clear error naming the
tool/ticker/date so the gap is obvious rather than masked by empty input.


## Artifacts and Notes

Representative builder summary (illustrative):

    Arctic Shift archive validation — data/raw-backtest/arctic-shift
    AAPL   pages=62   posts=<parsed>   ticker-day rows=61
    GOOGL  pages=84   posts=<parsed>   ticker-day rows=61
    AMZN   pages=64   posts=<parsed>   ticker-day rows=61
    Reddit payloads rendered offline; no live social-source requests made.

    StockTwits archive validation — data/raw-backtest/stocktwits
    AAPL   pages=10983  cutoff=2023-12-18 reached
    GOOGL  pages=3562   cutoff=2023-12-18 reached
    AMZN   pages=6620   cutoff=2023-12-18 reached
    StockTwits payloads rendered offline; no live social-source requests made.

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

Known limitations to keep in mind: the trading-day count is derived from the actual
price calendar and equals the README's 61 (2024-01-02 ..
2024-03-28, with 2024-03-29 a closed holiday); and the full run is
language-model-expensive (3 × 61 = 183 flow
runs), which is why `--limit-days` exists.


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
        def put_tool_outputs(self, rows: list[tuple[str, str, str, str]]) -> None: ...
        def put_prices(self, symbol: str, rows: list[tuple[str, float]]) -> None: ...

In `src/trading_agents/tools/market_data.py`:

    INDICATOR_WARMUP_YEARS = 5
    INDICATOR_MIN_WARMUP_ROWS = 200
    def indicator_calculation_start_date(start_date: str) -> str: ...
    def download_indicator_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame: ...
    def render_indicators_text(ticker: str, start_date: str, end_date: str, indicators: list[str], history: pd.DataFrame) -> str: ...

In `src/trading_agents/evaluation/backtest.py`:

    def simulate_position(decisions: list[tuple[str, str]], closes: dict[str, float], weight_over: float, weight_under: float) -> "BacktestResult": ...
    def cumulative_return(result: "BacktestResult", weight_over: float) -> float: ...

In `src/trading_agents/evaluation/exa_sources.py`:

    def fetch_news_via_exa(query: str, start_date: str, end_date: str, limit: int) -> str: ...
    def fetch_global_news_via_exa(curr_date: str, look_back_days: int, limit: int) -> str: ...

In `src/trading_agents/evaluation/build_dataset.py` and `run_eval.py`, a `main()` each,
registered as `build-eval-dataset` and `run-eval` in `pyproject.toml`.

In `src/trading_agents/evaluation/build_dataset.py`, define builder helpers with these
observable behaviors:

    def main(argv: list[str] | None = None) -> int: ...
    def load_arctic_shift_posts(raw_dir: Path, tickers: list[str]) -> "ArcticShiftArchive": ...
    def validate_arctic_shift_coverage(archive: "ArcticShiftArchive", tickers: list[str], trade_dates: list[str]) -> None: ...
    def load_stocktwits_messages(raw_dir: Path, tickers: list[str]) -> "StockTwitsArchive": ...
    def validate_stocktwits_coverage(archive: "StockTwitsArchive", tickers: list[str], trade_dates: list[str]) -> None: ...
    def build_dataset(tickers: list[str], limit_days: int | None = None) -> "BuildSummary": ...
    def build_price_table(options: "BuildDatasetOptions", dataset: EvalDataset) -> "PriceBuildResult": ...

`main()` parses `--tickers` and `--limit-days`. The archive loaders must expose enough
structured data for tests to assert page validation, numeric filename ordering,
duplicate handling, and ticker/date coverage. `build_dataset()` and non-social builders
must not depend on social archive ingestion.

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

Revision Note: 2026-07-16 The `fetch_reddit_posts` source gate is open. Historical Arctic
Shift API responses have been retained under `data/raw-backtest/arctic-shift/` (210 JSON
pages: AAPL 62, GOOGL 84, AMZN 64). Plan 07 now specifies offline validation, parsing,
deduplication, and rendering of that archive; it removes the live Exa/Reddit availability
probe and replacement-period scan from the implementation path. This changes neither the
live Reddit RSS behavior nor any plan implementation status.

Revision Note: 2026-07-16 The `fetch_stocktwits_messages` source gate is also open.
Commit `a33bee20c7f866df994e8ca70c310cc9cd992ca1` records successful Stage 1 and Stage
2 coverage scans. The retained archive under `data/raw-backtest/stocktwits/` contains
21,165 pagination JSON pages (AAPL 10,983, GOOGL 3,562, AMZN 6,620), with all terminal
sequences reaching before the Plan 07 2023-12-18 two-week-lookback cutoff. Plan 07 now
specifies offline validation, numeric ordering, deduplication, and rendering of this
archive rather than Exa search or live StockTwits pagination. This changes neither live
StockTwits behavior nor any plan implementation status.

Revision Note: 2026-07-17 Implemented and populated canonical Arctic Shift Reddit
ingestion. This revision records the offline validation contract, live-equivalent
quality filtering and rich rendering, raw engagement-field preservation, focused test
evidence, and the resulting 1,051 raw/183 replay-row dataset coverage.

Revision Note: 2026-07-17 Implemented and populated canonical StockTwits archive
ingestion. This revision records strict numeric pagination, schema/cursor/chronology and
coverage validation, deterministic internal-page sorting, the 21,165-page validation
evidence, and the resulting 183 full replay payloads.

Revision Note: 2026-07-17 Re-audited the populated DuckDB artifact before declaring it
ready. This revision records complete row coverage and the absence of stored API errors,
but adds remediation work for Reddit no-data rows, indicator warm-up blanks,
point-in-time-unsafe fundamentals/statements, future or unrelated news contamination,
and future-dated raw Reddit rows.

Revision Note: 2026-07-17 Replaced Reddit engagement filtering with upstream recent-post
selection, added upstream named empty-subreddit and aggregate empty messages, and
atomically rebuilt all 183 canonical Reddit payloads. This resolves the six misleading
GOOGL no-data outputs while preserving score/comment metadata for display. The remaining
dataset-readiness findings are unchanged.

Revision Note: 2026-07-17 Added five years of pre-window OHLCV to indicator calculation,
with one reusable download per ticker and output trimmed to the analyst lookback window.
Atomically rebuilt all 183 indicator payloads and verified zero blank requested-indicator
cells, boundary errors, row-count errors, or fresh-render mismatches. This resolves the
first-row Bollinger blanks and initializes long-window and recursive indicators; the
remaining dataset-readiness findings are unchanged.

Revision Note: 2026-07-17 Normalized dividend-yield fallback units and atomically
replaced the 61 AMZN fundamentals payloads. Yahoo's explicit trailing zero now renders
as `Dividend yield: 0` rather than `Missing fields: Dividend yield`; all unrelated tool
outputs remained unchanged. This was later superseded by the SEC point-in-time
fundamentals refresh.

Revision Note: 2026-07-17 Replaced all 183 `get_fundamentals` rows with SEC-backed
point-in-time fundamentals and archived the required filings under
`data/raw-backtest/SEC`. The refreshed fundamentals rows use only filings and closes
strictly before each replay date, all stale Yahoo snapshot markers are gone, and the
full suite reports 201 passed. Point-in-time-unsafe yfinance statement rows remain
pending.

Revision Note: 2026-07-18 Replaced all 183 `get_balance_sheet` rows with SEC-backed
point-in-time statements using the existing validated filing archive. The refreshed
rows select filings strictly before each replay date, contain only periods disclosed by
the selected accession, and pass zero-issue filing-date and fiscal-period audits. The
cash-flow and income-statement snapshot findings remain pending.

Revision Note: 2026-07-18 Replaced all 183 `get_cashflow` rows with SEC-backed
point-in-time statements using the existing validated filing archive. The refreshed
rows select form-appropriate annual or fiscal-year-to-date periods from the selected
accession, derive free cash flow, and pass zero-issue filing-date, period, accession,
and cash-reconciliation audits. The then-pending income-statement snapshot finding is
resolved by the following revision.

Revision Note: 2026-07-18 Replaced all 183 `get_income_statement` rows with SEC-backed
point-in-time statements using the existing validated filing archive. The refreshed
rows select annual 10-K or quarterly 10-Q periods from the selected accession and pass
zero-issue filing-date, period, accession, gross-profit, net-income, and EPS audits.
This resolves the final point-in-time financial-statement finding.
