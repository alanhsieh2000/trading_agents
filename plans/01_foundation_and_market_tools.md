# Make the Project Installable and Add Trading Data Tools

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can be installed and the future TradingAgents crews can call real, named financial data tools instead of relying on placeholder code or unsupported agent memory. A user can run deterministic tests for the tool layer without an LLM key, and later crews can ask for prices, technical indicators, fundamentals, news, and sentiment context using the same tool names described in `README.md`.

This plan deliberately starts with installation and tools because every downstream agent depends on them. If analysts do not have working tools, they will fabricate market data.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, `PLANS.md`, `AGENTS.md`, the project-local CrewAI skills under `.agents/skills`, and the current source skeleton.
- [x] (2026-05-23 14:20Z) Confirmed that `plans/` exists and is empty before this plan series was drafted.
- [x] (2026-05-23 14:20Z) Confirmed that `uv run python -c "import crewai; print(crewai.__version__)"` failed during dependency resolution before the dependency fix.
- [x] (2026-05-23 14:58Z) Rechecked after the user's fix and confirmed `uv run python -c "import crewai; print(crewai.__version__)"` prints `1.14.5`.
- [x] (2026-05-23 15:03Z) Made the local package installable by changing `pyproject.toml` to project name `trading-agents`, adding `hatchling` build metadata, adding console scripts, and preserving `[tool.crewai] type = "flow"`.
- [x] (2026-05-23 15:07Z) Replaced the placeholder `src/trading_agents/tools/custom_tool.py` with focused trading tool modules and exports.
- [x] (2026-05-23 15:11Z) Added deterministic tests in `tests/test_trading_tools.py` with monkeypatched `yfinance` and HTTP helpers.
- [x] (2026-05-23 15:14Z) Ran `uv run pytest tests/test_trading_tools.py`; all 10 tests passed.
- [x] (2026-05-23 15:15Z) Ran the plan acceptance smoke commands and the full test suite; CrewAI imports, the local `trading_agents` package imports, and all tests pass.

## Surprises & Discoveries

- Observation: The original dependency failure is resolved in the current environment.
  Evidence: From `/app/trading_agents`, `uv run python -c "import crewai; print(crewai.__version__)"` prints `1.14.5`.
- Observation: PyPI currently reports CrewAI `1.14.5` as the package release while the installed version is also `1.14.5`.
  Evidence: `https://pypi.org/pypi/crewai/json` reports release URL `https://pypi.org/project/crewai/1.14.5/` and the installed command above prints `1.14.5`.
- Observation: The official CrewAI tools documentation still uses the `BaseTool` plus Pydantic `args_schema` custom-tool pattern.
  Evidence: `https://docs.crewai.com/en/concepts/tools` shows subclassing `BaseTool` with `args_schema: Type[BaseModel]` and `_run(...)`; the implementation follows that pattern.
- Observation: The official changelog page available during implementation topped out at `v1.12.1`, behind the PyPI package version, so it did not show `1.14.5` release notes.
  Evidence: `https://docs.crewai.com/en/changelog` showed `v1.12.1` at the top when checked on 2026-05-23.
- Observation: Importing `crewai` succeeded after dependency resolution, but importing `trading_agents` did not work until the local project was made installable.
  Evidence: Before the `pyproject.toml` package metadata change, `uv run python -c "from trading_agents.tools import get_stock_data"` raised `ModuleNotFoundError: No module named 'trading_agents'`. After `uv sync`, the command prints `get_stock_data`.
- Observation: The sandboxed patch helper and sandboxed `uv sync` both failed with a namespace error in this environment.
  Evidence: The error was `bwrap: No permissions to create a new namespace`. The file changes were applied with a one-off Python writer because patching could not run, and `uv sync` succeeded after escalation.
- Observation: `stockstats.StockDataFrame` keeps the date as the index during indicator column selection, so the implementation must convert back to a plain pandas `DataFrame` before formatting output.
  Evidence: The first test run failed in `test_indicators_format_requested_values` with `UserWarning: Invalid number of return arguments after parsing column name: 'date'`. Converting with `pd.DataFrame(...).reset_index()` fixed the issue and the suite passed.
- Observation: The original TradingAgents Reddit implementation no longer relies on
  Reddit's public `/search.json` endpoint as the default path.
  Evidence: `https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/dataflows/reddit.py`
  documents that `/search.json` is WAF-blocked for public clients and uses
  `/search.rss` first. A local probe on 2026-06-15 for
  `https://www.reddit.com/r/wallstreetbets/search.rss?q=AAPL&restrict_sr=on&sort=new&t=week&limit=5`
  returned HTTP 200 with two Atom entries, while the equivalent `.json` endpoint
  returned HTTP 403 in the same environment.

## Decision Log

- Decision: Fix the local project dependency pin before writing CrewAI code.
  Rationale: The project cannot import CrewAI or run tests from its own root while dependency resolution fails. All other plans depend on this being stable.
  Date/Author: 2026-05-23 / Codex
- Decision: Prefer a stable CrewAI dependency constraint over requiring prerelease resolution.
  Rationale: The repository root now uses `crewai[tools]>=1.14.5`, while the earlier project-local `crewai[tools]==1.14.5a2` failed. Using a stable lower bound keeps installation repeatable unless later research proves a specific prerelease is required.
  Date/Author: 2026-05-23 / Codex
- Decision: Build trading tools as local `BaseTool` subclasses with exact tool names matching the original TradingAgents prompts.
  Rationale: `README.md` says prompts and tools should stay close to the original project, including tool names. CrewAI agents need actual tool instances, not only prompt text.
  Date/Author: 2026-05-23 / Codex
- Decision: Rename the Python project from `app` to `trading-agents` and add `hatchling` build metadata for `src/trading_agents`.
  Rationale: `uv run` can import installed dependencies, but the local package was not installable without build metadata. The package name now matches the repository purpose and the import package remains `trading_agents`.
  Date/Author: 2026-05-23 / Codex
- Decision: Delete `src/trading_agents/tools/custom_tool.py` instead of keeping a compatibility wrapper.
  Rationale: No source code imported `MyCustomTool`, and keeping the scaffold placeholder would make it unclear which tools are real. The public tool surface now lives in `src/trading_agents/tools/__init__.py`.
  Date/Author: 2026-05-23 / Codex
- Decision: Implement `get_global_news` through Yahoo Finance index ticker feeds `^GSPC`, `^IXIC`, and `^DJI`, and include a source-limitation sentence in every result.
  Rationale: This keeps the first implementation dependency-light and testable while honestly telling agents that the source is not a full macro-news provider.
  Date/Author: 2026-05-23 / Codex
- Decision: Keep sentiment prefetching as plain functions, not CrewAI tools.
  Rationale: The original TradingAgents sentiment flow prefetches StockTwits and Reddit context into prompts rather than exposing those calls as tools. Later analyst crews can inject these strings directly.
  Date/Author: 2026-05-23 / Codex
- Decision: Fix the live Reddit sentiment helper with an RSS-first implementation.
  Rationale: The current helper still calls Reddit `/search.json`, which can be
  blocked with HTTP 403 and then masked as `No data available`. The original
  TradingAgents implementation uses `/search.rss` first and treats JSON as a future
  OAuth-capable fallback. The local port should follow that pattern, omit score and
  comment counts for RSS results rather than fabricating them, and preserve the
  existing plain-string prompt contract.
  Date/Author: 2026-06-15 / Codex

## Outcomes & Retrospective

This plan is implemented. The project now installs as `trading-agents`, imports CrewAI `1.14.5`, exports the planned TradingAgents-compatible tool names, and passes deterministic tests without live network calls.

The main code outcome is a focused tool package under `src/trading_agents/tools/`. Market data tools return compact CSV-like price and indicator evidence. Fundamentals tools return company profile fields and compact financial statement CSV. News tools return headline summaries and explicit source limitations for global market news. Sentiment helpers return formatted StockTwits and Reddit snippets or clear `No data available` messages when upstream data is absent.

The main remaining architectural gap is that these tools are not yet wired into analyst crews. That is intentionally left for the analyst-crew plan because this foundation plan only establishes installability, tool names, and deterministic tool behavior.

Post-implementation follow-up: update `src/trading_agents/tools/sentiment.py` so
`fetch_reddit_posts` uses Reddit RSS/Atom search first, matching the original
TradingAgents implementation. This is a live-tool reliability fix, not a historical
backtest-data solution.

## Context and Orientation

The project root for this plan is `/app/trading_agents`. The current code is a CrewAI Flow scaffold generated around content writing, not trading. The relevant files after this implementation are:

- `pyproject.toml`, which declares package name `trading-agents`, dependencies, console scripts, `hatchling` build metadata for `src/trading_agents`, and `[tool.crewai] type = "flow"`.
- `uv.lock`, which records the resolved dependencies and local package metadata after `uv sync`.
- `src/trading_agents/main.py`, which currently defines `ContentState` and `ContentFlow`.
- `src/trading_agents/crews/content_crew/content_crew.py`, a reference CrewAI `@CrewBase` class. Keep it as a reference unless a later plan explicitly removes it.
- `src/trading_agents/tools/market_data.py`, which defines `get_stock_data` and `get_indicators`.
- `src/trading_agents/tools/fundamentals.py`, which defines `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`.
- `src/trading_agents/tools/news.py`, which defines `get_news` and `get_global_news`.
- `src/trading_agents/tools/sentiment.py`, which defines `fetch_stocktwits_messages` and `fetch_reddit_posts`.
- `src/trading_agents/tools/__init__.py`, which exports the public tool and helper names.
- `tests/test_trading_tools.py`, which tests all tool modules with local fixtures and monkeypatching.
- `tests/eval_cases/trading_agent_eval_cases.yaml`, an untracked evaluation-case file that was not deleted or overwritten.

Definitions used in this plan:

A CrewAI tool is a Python object, usually a subclass of `crewai.tools.BaseTool`, that an agent can call to fetch data or perform a calculation. A CrewAI agent is a role-specific LLM worker. A CrewAI task is the assignment that an agent performs. A CrewAI flow is the outer orchestration class that stores state and calls crews or agents in order. Monkeypatching is a test technique where a test temporarily replaces a function such as `yfinance.download` with a local fake function so the test is deterministic and does not call a live service.

The tools in this plan are not responsible for making investment decisions. They only retrieve or compute evidence that later agents will analyze.

## Plan of Work

First, make the project installable. In `pyproject.toml`, use the stable dependency constraint `crewai[tools]>=1.14.5`, set the project name to `trading-agents`, add the console scripts that point to `trading_agents.main`, add `hatchling` as the build backend, and configure the wheel target to package `src/trading_agents`. Run `uv sync` from `/app/trading_agents` and keep `uv.lock` only after dependency resolution and package installation succeed.

Second, turn `src/trading_agents/tools/` into a small trading data package. Delete `custom_tool.py` because no generated scaffold imports it. Create these modules:

- `src/trading_agents/tools/market_data.py` for price history and technical indicators.
- `src/trading_agents/tools/fundamentals.py` for company profile and financial statements.
- `src/trading_agents/tools/news.py` for company and global news summaries.
- `src/trading_agents/tools/sentiment.py` for prefetch helpers used by the sentiment analyst.

Export the public tools from `src/trading_agents/tools/__init__.py` so crew modules can import them from one place.

The CrewAI tool names must match the original TradingAgents prompt names:

- `get_stock_data`
- `get_indicators`
- `get_news`
- `get_global_news`
- `get_fundamentals`
- `get_balance_sheet`
- `get_cashflow`
- `get_income_statement`

The sentiment helpers do not need to be CrewAI tools unless later implementation makes them agent-callable. Implement functions named `fetch_stocktwits_messages` and `fetch_reddit_posts` that return plain strings for prompt injection. They should degrade gracefully by returning a clear `No data available` message when credentials, network access, or upstream responses are unavailable.

Third, implement each tool with deterministic boundaries. Use `yfinance` for market history, company information, financial statements, and Yahoo Finance news where practical. Use `pandas` and `stockstats` for technical indicators. Keep the output text compact but evidence-rich: include ticker, date range, rows covered, values used, and a warning when data is missing.

The market tool behavior is:

- `get_stock_data(ticker, start_date, end_date)` returns CSV-like text with date, open, high, low, close, adjusted close when available, and volume.
- `get_indicators(ticker, start_date, end_date, indicators)` computes only requested indicators from this allowed set: `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`.
- If an indicator name is not in the allowed set, return a validation error listing the allowed names instead of guessing.

The fundamentals tool behavior is:

- `get_fundamentals(ticker)` returns a concise company profile, sector, industry, market capitalization, trailing and forward valuation fields where available, and a note about missing values.
- `get_balance_sheet(ticker)`, `get_cashflow(ticker)`, and `get_income_statement(ticker)` return the most recent available statements as compact CSV text.

The news tool behavior is:

- `get_news(query, start_date, end_date, limit)` returns company-specific or query-specific headlines, timestamps, publisher/source where available, and URLs if available.
- `get_global_news(curr_date, look_back_days, limit)` returns broad market headlines from Yahoo Finance index feeds and explicitly says that global news currently uses those index feeds.

Fourth, add tests that use monkeypatching rather than live network calls. Create `tests/test_trading_tools.py` to replace `yfinance.Ticker`, `yfinance.download`, and HTTP JSON fetches with small local fixtures. Test successful output, empty upstream output, invalid indicator names, statement formatting, news filtering, global-news limit handling, and sentiment degradation.

## Concrete Steps

Run commands from `/app/trading_agents` unless a step states otherwise.

1. Verify CrewAI imports:

       uv run python -c "import crewai; print(crewai.__version__)"

   Observed after implementation:

       1.14.5

2. Synchronize dependencies and install the local package:

       uv sync

   Observed successful output included:

       Building trading-agents @ file:///app/trading_agents
       Built trading-agents @ file:///app/trading_agents
       Installed 1 package in 1ms
       + trading-agents==0.1.0 (from file:///app/trading_agents)

3. Verify the public tool imports:

       uv run python -c "from trading_agents.tools import get_stock_data, get_indicators, get_fundamentals; print(get_stock_data.name, get_indicators.name, get_fundamentals.name)"

   Observed output:

       get_stock_data get_indicators get_fundamentals

4. Run the focused test suite:

       uv run pytest tests/test_trading_tools.py

   Observed success:

       tests/test_trading_tools.py ..........                                   [100%]
       10 passed in 2.49s

5. Run the full current test suite:

       uv run pytest

   Observed success:

       tests/test_trading_tools.py ..........                                   [100%]
       10 passed in 2.67s

## Validation and Acceptance

This plan is accepted when a user can run the following from `/app/trading_agents`:

    uv run python -c "import crewai; print(crewai.__version__)"
    uv run pytest tests/test_trading_tools.py
    uv run python -c "from trading_agents.tools import get_stock_data; print(get_stock_data.name)"

The first command must print a CrewAI version. The second command must pass without live network calls. The third command must print `get_stock_data`. These acceptance commands passed on 2026-05-23.

Acceptance also requires that invalid or missing data does not crash the tools. The tests cover invalid indicator names, empty price data, missing fundamentals, empty statements, news filtering, and sentiment fetch failures.

## Idempotence and Recovery

The dependency edit is safe to repeat. If `uv sync` updates `uv.lock`, keep the lockfile only when dependency resolution succeeds. If a sync attempt fails, leave `pyproject.toml` in the stable-constraint and packageable state and record the failure in this plan.

Tool tests must not call live services. If live service behavior is accidentally exercised in tests, replace it with monkeypatched fixtures before continuing.

Do not delete or overwrite `tests/eval_cases/trading_agent_eval_cases.yaml`. It is currently untracked and belongs to the user or generated project context.

If `uv sync` fails with the sandbox namespace error `bwrap: No permissions to create a new namespace`, rerun it outside the sandbox with approval. That is an environment issue, not a dependency issue.

## Artifacts and Notes

Current successful CrewAI import:

    uv run python -c "import crewai; print(crewai.__version__)"
    1.14.5

Current successful focused test run:

    uv run pytest tests/test_trading_tools.py
    tests/test_trading_tools.py ..........                                   [100%]
    10 passed in 2.49s

Current successful export smoke test:

    uv run python -c "from trading_agents.tools import get_stock_data; print(get_stock_data.name)"
    get_stock_data

Historical dependency failure observed while drafting:

    uv run python -c "import crewai; print(crewai.__version__)"
      x No solution found when resolving dependencies:
      Because there is no version of crewai-tools==1.14.5a2 ...

Historical virtualenv import failure observed while drafting:

    .venv/bin/python -c "import crewai; print(crewai.__version__)"
    ModuleNotFoundError: No module named 'crewai'

Important upstream tool-name source map from the original TradingAgents files named in `README.md`:

- Fundamentals analyst uses `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`.
- News analyst uses `get_news` and `get_global_news`.
- Market analyst uses `get_stock_data` and `get_indicators`.
- Sentiment analyst prefetches news, StockTwits messages, and Reddit posts into the prompt rather than using tool calling.

## Interfaces and Dependencies

At the end of this plan, the following names exist:

    # src/trading_agents/tools/__init__.py
    get_stock_data
    get_indicators
    get_news
    get_global_news
    get_fundamentals
    get_balance_sheet
    get_cashflow
    get_income_statement
    fetch_stocktwits_messages
    fetch_reddit_posts

Each CrewAI tool exposes a `.name` matching the original tool name exactly. The CrewAI tools are `BaseTool` subclasses with Pydantic argument schemas so CrewAI can validate tool calls.

Use existing project dependencies where possible:

- `yfinance` for prices, company metadata, financial statements, and Yahoo Finance news.
- `pandas` for dataframe normalization and compact CSV rendering.
- `stockstats` for technical indicators.
- Standard-library `urllib` for sentiment helper JSON calls so no extra HTTP dependency is required for this plan.
- `hatchling` as the project build backend so `uv sync` can install `src/trading_agents` as the local package.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading `README.md`, `PLANS.md`, `AGENTS.md`, project-local CrewAI skills, and the current source skeleton. The plan starts with dependency repair because all later CrewAI work depends on a runnable project.

Revision Note: 2026-05-23 15:16Z Implemented the plan after the user fixed the `uv run` dependency issue. Updated the document with the package metadata changes, new trading tool modules, deterministic tests, sandbox discovery, validation transcripts, and completion outcome.
