# Plan 07b StockTwits Coverage Scanner

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.


## Purpose / Big Picture

After this change, a contributor can verify whether the unauthenticated StockTwits
symbol stream can be paginated far enough back to support both evaluation windows:

- Plan B: two-week sentiment lookback before `2026-01-01`, requiring coverage to
  at least `2025-12-18`.
- Plan 07: two-week sentiment lookback before `2024-01-01`, requiring coverage to
  at least `2023-12-18`.

The scanner stores raw StockTwits JSON responses under
`data/raw-backtest/stocktwits/{ticker}-{sequence}.json`. It resumes from existing
files and uses the previous response's `cursor.max` as the next request's `max`
parameter. The two existing AAPL files are seed data and must not be overwritten.

Run from the project root:

    uv run scan-stocktwits-coverage

The command exits successfully only if the attempted stage reaches its required
cutoff for every configured evaluation ticker. Stage 2 is attempted only after
Stage 1 succeeds for all tickers.


## Progress

- [x] Added `src/trading_agents/evaluation/stocktwits_coverage.py`, a standalone
  StockTwits scanner that resumes raw JSON sequences, paginates with `cursor.max`,
  sleeps between requests, writes files atomically, and reports per-ticker coverage.
- [x] Added the `scan-stocktwits-coverage` console script.
- [x] Added mocked unit tests for first-page requests, `max` pagination, resume
  behavior, cutoff stopping, `cursor.more` stopping, and inter-request delays.
- [x] Added `--max-files` to cap the number of new JSON files downloaded by one
  scanner invocation.
- [ ] Run the live scanner for AAPL, GOOGL, and AMZN through Stage 1.
  A foreground attempt on 2026-07-14 was manually interrupted after writing
  `AAPL-0003.json` through `AAPL-0027.json`; AAPL had only reached
  `2026-07-09T15:45:05Z`, so Stage 1 did not complete.
- [ ] If Stage 1 succeeds for all three tickers, continue through Stage 2.
- [ ] Record the live scan output and per-ticker coverage summary in
  `Outcomes & Retrospective`.


## Surprises & Discoveries

- Observation: The seed AAPL files show StockTwits pagination through `cursor.max`.
  Evidence: `AAPL-0001.json` has `cursor.max=658863672`; `AAPL-0002.json` was
  fetched with that value and has older messages plus a new `cursor.max=658857991`.
- Observation: AAPL message volume is high enough that the original 10-second
  inter-request delay makes the Stage 1 scan a long-running data collection job.
  Evidence: A foreground `uv run scan-stocktwits-coverage` attempt on 2026-07-14
  wrote 25 additional AAPL pages, reaching `AAPL-0027.json`; that file's oldest
  message was still `2026-07-09T15:45:05Z`, far short of the `2025-12-18` Stage 1
  cutoff, and `cursor.more` was still true.
- Observation: Shorter AAPL pagination delays did not immediately hit the StockTwits
  API rate limit in a small probe.
  Evidence: On 2026-07-14, a controlled continuation wrote five pages each with
  4-second, 2-second, and 1-second delays. The 4-second probe wrote `AAPL-0028.json`
  through `AAPL-0032.json`, the 2-second probe wrote `AAPL-0033.json` through
  `AAPL-0037.json`, and the 1-second probe wrote `AAPL-0038.json` through
  `AAPL-0042.json`; no HTTP error or 429 occurred. `AAPL-0042.json` had oldest
  message `2026-07-08T14:19:26Z` and `cursor.more=True`.
- Observation: The scanner default was reduced to a 1-second inter-request delay
  after the short delay probe.
  Evidence: The probe wrote five consecutive AAPL pages at 1-second spacing without
  HTTP errors or 429s; `scan-stocktwits-coverage` now defaults `--delay` to `1.0`.
- Observation: Capped AAPL timing runs at the 1-second default delay completed
  without HTTP errors while preserving all fetched pages.
  Evidence: On 2026-07-14, `--max-files 10` downloaded 10 files in 15.990 seconds,
  `--max-files 20` downloaded 20 files in 29.044 seconds, `--max-files 50`
  downloaded 50 files in 69.320 seconds, and `--max-files 100` downloaded 100 files
  in 131.488 seconds. The run advanced AAPL from `AAPL-0042.json` through
  `AAPL-0222.json`; `AAPL-0222.json` had oldest message `2026-06-22T13:31:04Z`
  and `cursor.more=True`.
- Observation: The scanner now defaults to 100 new JSON files per invocation and
  prints an estimated duration before fetching.
  Evidence: The default `--max-files` is 100. With the default 1-second delay and
  the observed AAPL timing, the command prints `It may take 132 seconds.` before
  starting Stage 1.

Add new observations here as they arise, with a short evidence snippet.


## Decision Log

- Decision: Store raw StockTwits API responses as JSON files before integrating them
  into DuckDB replay payloads.
  Rationale: The immediate risk is historical coverage, not prompt rendering. Raw
  files preserve the source responses for audit and make later dataset integration
  deterministic.
  Date/Author: 2026-07-14 / Codex

- Decision: Use `2025-12-18` as the Stage 1 cutoff and `2023-12-18` as the Stage 2
  cutoff.
  Rationale: Each date is two weeks before the corresponding evaluation start date,
  matching the user's requested coverage gate.
  Date/Author: 2026-07-14 / Codex

- Decision: Run Stage 2 only if Stage 1 succeeds for AAPL, GOOGL, and AMZN.
  Rationale: If the API cannot cover Plan B for every ticker, continuing to the
  older Plan 07 cutoff would waste requests and increase rate-limit risk.
  Date/Author: 2026-07-14 / Codex

- Decision: Use a 1-second default delay between every two StockTwits API calls,
  including ticker transitions.
  Rationale: A controlled AAPL probe succeeded at 4-second, 2-second, and 1-second
  delays for five pages each with no HTTP errors, and the 10-second delay made the
  scan impractically slow for high-volume tickers.
  Date/Author: 2026-07-14 / Codex


## Implementation Notes

- The first request for a ticker omits `max` unless prior files exist.
- When prior files exist, the scanner reads the highest sequence file, resumes at
  the next sequence number, and uses that file's `cursor.max`.
- The scanner stops a ticker when the oldest observed `messages[*].created_at`
  reaches the stage cutoff or when `cursor.more` is false.
- `--max-files N` stops the current invocation after writing at most `N` new JSON
  files. The cap applies across tickers and stages, and defaults to 100.
- Before scanning, the CLI prints `It may take {need_seconds} seconds.` using a
  rounded-up estimate from `max_files` and the configured delay.
- Existing files are never overwritten; new responses are written atomically.
- The default output directory is `data/raw-backtest/stocktwits`.
- CLI options:
  - `--tickers AAPL GOOGL AMZN`
  - `--output-dir data/raw-backtest/stocktwits`
  - `--delay 1`
  - `--max-files 100`
  - `--stage1-only`
  - `--stage1-cutoff YYYY-MM-DD`
  - `--stage2-cutoff YYYY-MM-DD`


## Outcomes & Retrospective

Live attempt 1 — partial AAPL scan (2026-07-14). Ran:

    uv run scan-stocktwits-coverage

The command resumed from the existing AAPL seed files and wrote
`AAPL-0003.json` through `AAPL-0027.json` under
`data/raw-backtest/stocktwits/`. It was manually interrupted while sleeping before
the next request because the scan had not completed Stage 1 after several minutes.
The latest file at interruption time was:

    AAPL-0027.json newest=2026-07-09T16:26:09Z oldest=2026-07-09T15:45:05Z cursor={'more': True, 'since': 658670699, 'max': 658664599}

GOOGL and AMZN had not started yet because Stage 1 processes tickers sequentially
and this first attempt used a 10-second delay between every two API calls. The
scanner is resumable; the later delay probe continued with `AAPL-0028.json` using
`AAPL-0027.json`'s `cursor.max`.

Live delay probe — AAPL only (2026-07-14). A controlled continuation fetched five
more AAPL pages at each shorter delay:

    delay=4s: AAPL-0028.json..AAPL-0032.json, no HTTP error
    delay=2s: AAPL-0033.json..AAPL-0037.json, no HTTP error
    delay=1s: AAPL-0038.json..AAPL-0042.json, no HTTP error

The latest file after the probe was:

    AAPL-0042.json newest=2026-07-08T15:06:10Z oldest=2026-07-08T14:19:26Z cursor={'more': True, 'since': 658554887, 'max': 658546830}

This small probe suggests StockTwits tolerates at least short bursts at 1-second
spacing from this environment, but it does not prove a full multi-hour scan will
avoid rate limits.

Live capped timing run — AAPL only (2026-07-14). Ran four resumable capped batches
at the default 1-second delay:

    max_files=10  before=42  after=52   downloaded=10   elapsed_seconds=15.990
    max_files=20  before=52  after=72   downloaded=20   elapsed_seconds=29.044
    max_files=50  before=72  after=122  downloaded=50   elapsed_seconds=69.320
    max_files=100 before=122 after=222  downloaded=100  elapsed_seconds=131.488

No HTTP errors or 429s occurred. The latest file after the capped timing run was:

    AAPL-0222.json newest=2026-06-22T14:37:52Z oldest=2026-06-22T13:31:04Z cursor={'more': True, 'since': 657053125, 'max': 657038191}

The raw StockTwits folder was approximately 24 MB after this run. AAPL still had
not reached the Stage 1 cutoff.
