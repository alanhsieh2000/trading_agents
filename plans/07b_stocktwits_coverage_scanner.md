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
- [ ] If Stage 1 succeeds for all three tickers, continue through Stage 2.
- [ ] Record the live scan output and per-ticker coverage summary in
  `Outcomes & Retrospective`.


## Surprises & Discoveries

- Observation: The seed AAPL files show StockTwits pagination through `cursor.max`.
  Evidence: `AAPL-0001.json` has `cursor.max=658863672`; `AAPL-0002.json` was
  fetched with that value and has older messages plus a new `cursor.max=658857991`.

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

No live StockTwits coverage scan has been completed yet.
