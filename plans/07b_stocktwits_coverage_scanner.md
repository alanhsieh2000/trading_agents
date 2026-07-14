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
- Observation: AAPL message volume is high enough that the required 10-second
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

- Decision: Use a 10-second delay between every two StockTwits API calls, including
  ticker transitions.
  Rationale: The user explicitly requested this delay to reduce API rate-limit risk.
  Date/Author: 2026-07-14 / Codex


## Implementation Notes

- The first request for a ticker omits `max` unless prior files exist.
- When prior files exist, the scanner reads the highest sequence file, resumes at
  the next sequence number, and uses that file's `cursor.max`.
- The scanner stops a ticker when the oldest observed `messages[*].created_at`
  reaches the stage cutoff or when `cursor.more` is false.
- Existing files are never overwritten; new responses are written atomically.
- The default output directory is `data/raw-backtest/stocktwits`.
- CLI options:
  - `--tickers AAPL GOOGL AMZN`
  - `--output-dir data/raw-backtest/stocktwits`
  - `--delay 10`
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
with a 10-second delay between every two API calls. The scanner is resumable; a
future run will continue with `AAPL-0028.json` using `AAPL-0027.json`'s
`cursor.max`.

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
