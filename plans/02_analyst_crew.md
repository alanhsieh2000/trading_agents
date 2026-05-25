# Implement the Analyst Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project has a CrewAI Analyst Crew that produces four separate markdown reports for a ticker and date: market, sentiment, news, and fundamentals analysis. The Analyst Crew now follows `PROMPTS.md`: one shared Analyst agent performs four focused tasks in sequence, and each task receives only the tools it needs. A user can run the analyst stage and inspect the four evidence-backed reports before any debate or trading decision happens.

This is the first user-visible TradingAgents stage. It turns raw data into report artifacts that later crews can debate.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the required Analyst Team reports, task outputs, and upstream TradingAgents source URLs.
- [x] (2026-05-23 14:20Z) Read the reference CrewAI scaffold and CrewAI skills for YAML, `@CrewBase`, agents, tasks, tools, and task sequencing.
- [x] (2026-05-24 01:17Z) Created `src/trading_agents/crews/analyst_crew/` with `AnalystCrew`, YAML agent configuration, and YAML task configuration.
- [x] (2026-05-24 02:55Z) Added explicit `llm: gpt-4o-mini` settings to the analyst agent YAML and imported `load_dotenv()` before live kickoff.
- [x] (2026-05-24 06:57Z) Verified tracing is a `Crew`/`Flow` argument rather than a `Task` argument and enabled `tracing=True` on the analyst crew.
- [x] (2026-05-25 04:53Z) Read `PROMPTS.md` and changed the implementation from four specialized analyst agents to one shared `analyst` agent with four sequential tasks.
- [x] (2026-05-25 04:53Z) Moved tool access from agents to task constructors: market gets `get_stock_data` and `get_indicators`, news gets `get_news` and `get_global_news`, fundamentals gets the fundamentals statement tools, and sentiment gets no tools.
- [x] (2026-05-25 04:53Z) Updated `agents.yaml` and `tasks.yaml` to match the role, goal, backstory, task descriptions, expected outputs, and task order from `PROMPTS.md`.
- [x] (2026-05-25 04:53Z) Updated focused analyst tests for the single-agent, task-tool, sequential kickoff contract.
- [x] (2026-05-25 04:53Z) Ran `uv run pytest tests/test_analyst_crew_config.py`; all 9 analyst tests passed.
- [x] (2026-05-25 04:53Z) Ran `uv run pytest`; all 22 deterministic tests passed.
- [x] (2026-05-25 06:19Z) Confirmed the analyst YAML files do not use `{trade_date}` and updated input preparation so `{end_date}` is always `{current_date}`.
- [x] (2026-05-25 06:19Z) Made `{start_date}` and `{sentiment_start_date}` automatic seven-day lookbacks from `{current_date}` based on the past-week language in the prompts.
- [x] (2026-05-25 06:19Z) Added regression tests for current-date prompt variables and news prefetch date windows; `uv run pytest tests/test_analyst_crew_config.py` now has 11 passing tests.
- [x] (2026-05-25 06:19Z) Ran `uv run pytest`; all 24 deterministic tests passed.

## Surprises & Discoveries

- Observation: Installed CrewAI is current against the latest stable PyPI release.
  Evidence: `uv run python -c "import crewai; print(crewai.__version__)"` printed `1.14.5`, and PyPI showed `1.14.5` as the current stable release on 2026-05-25, with newer prereleases only.
- Observation: CrewAI supports task-level tools, which is required by the new Analyst Crew design.
  Evidence: The official Tasks documentation lists `tools` as a `Task` attribute and states that task tools limit or override the agent's tool set for that task.
- Observation: CrewAI executes tasks in definition order for `Process.sequential`.
  Evidence: The official Crews documentation states that sequential-process tasks run one after another in the order they are defined.
- Observation: The prompt variables in `PROMPTS.md` use `current_date`, `start_date`, `end_date`, `asset_label`, and `news_block`, while the existing flow used `trade_date`, `sentiment_start_date`, and `news_sentiment_block`.
  Evidence: The analyst YAML files now contain no `{trade_date}` placeholder. `prepare_analyst_inputs` treats `current_date` as the prompt date, keeps `trade_date` only as an external compatibility alias that is normalized to `current_date`, sets `end_date` equal to `current_date`, computes both `start_date` and `sentiment_start_date` as seven calendar days before `current_date`, and keeps both `news_block` and `news_sentiment_block` aliases.
- Observation: The dedicated `apply_patch` tool failed in this environment because the sandbox could not create a namespace.
  Evidence: Patch attempts failed with `bwrap: No permissions to create a new namespace`. The file edits were made by writing deterministic file contents from a local `uv run python` command.

## Decision Log

- Decision: Use one CrewAI agent named `analyst` for the analyst stage.
  Rationale: `PROMPTS.md` explicitly defines a single Analyst role, goal, and backstory. The four analysis perspectives are task differences, not separate CrewAI agent identities.
  Date/Author: 2026-05-25 / Codex
- Decision: Keep the agent runtime settings from the previous implementation: `llm: gpt-4o-mini`, `allow_delegation: false`, and `verbose: true`.
  Rationale: The requested change says `PROMPTS.md` specifies only role, goal, and backstory, and that the other settings should remain unchanged.
  Date/Author: 2026-05-25 / Codex
- Decision: Assign tools at task construction time in `analyst_crew.py` instead of on the shared agent.
  Rationale: A single agent performs all four tasks, but each task should expose a different tool surface. CrewAI task-level tools are the documented mechanism for that.
  Date/Author: 2026-05-25 / Codex
- Decision: Run the tasks sequentially in this exact order: `market_analysis`, `sentiment_analysis`, `news_analysis`, `fundamentals_analysis`.
  Rationale: `PROMPTS.md` describes the original analyst sequence as Market Analyst, Sentiment Analyst, News Analyst, then Fundamentals Analyst, and the requested implementation says tasks are not parallel anymore.
  Date/Author: 2026-05-25 / Codex
- Decision: Preserve the public report dictionary keys even though the internal task order changed.
  Rationale: The flow and later plans consume `market_report`, `sentiment_report`, `news_report`, and `fundamentals_report` by key, so keeping stable names avoids downstream churn.
  Date/Author: 2026-05-25 / Codex
- Decision: Treat `current_date` as the analyst prompt date and keep `trade_date` only as a compatibility input from the flow.
  Rationale: `PROMPTS.md` uses `{current_date}` in the Analyst system prompt and does not use `{trade_date}` in the YAML prompts. Existing flow code and evaluation cases still pass `trade_date`, so the prep helper maps that external field to `current_date` when needed.
  Date/Author: 2026-05-25 / Codex
- Decision: Derive `start_date` and `sentiment_start_date` automatically as seven days before `current_date`.
  Rationale: The sentiment and news prompts explicitly refer to the past seven days or past week. These values are prompt implementation details, not user-facing inputs.
  Date/Author: 2026-05-25 / Codex

## Outcomes & Retrospective

The analyst stage now matches `PROMPTS.md`. `AnalystCrew` has one `analyst` agent and four sequential tasks. Agent-level tools were removed; tools are attached to `market_analysis`, `news_analysis`, and `fundamentals_analysis` tasks, while `sentiment_analysis` receives pre-fetched prompt blocks and no tools.

Focused and full deterministic validation pass after the current-date correction. `uv run pytest tests/test_analyst_crew_config.py` reports 11 passing tests, and `uv run pytest` reports 24 passing tests across analyst config, flow, and trading-tool coverage.

## Context and Orientation

The project root is `/app/trading_agents`. The Analyst Crew implementation lives in `src/trading_agents/crews/analyst_crew/`. Its three important files are `analyst_crew.py`, `config/agents.yaml`, and `config/tasks.yaml`.

A CrewAI agent is the LLM worker. A CrewAI task is one concrete unit of work assigned to an agent. In this implementation there is one agent named `analyst`, and four tasks assigned to that same agent. A task-level tool is a tool list passed to `Task(...)`; CrewAI exposes those tools only while that task runs.

The input ticker is an exchange symbol such as `NVDA`. The analyst prompt date is `current_date`, an analysis date in `YYYY-MM-DD` format. The current flow still has an external `trade_date` field for compatibility, but the analyst YAML prompts use `current_date`. Technical indicators are mathematical features derived from price and volume history, such as RSI, MACD, Bollinger Bands, ATR, and moving averages.

## Plan of Work

`src/trading_agents/crews/analyst_crew/config/agents.yaml` must contain exactly one key, `analyst`. Its role, goal, and backstory come from `PROMPTS.md`. The existing runtime settings stay on that same agent: `llm: gpt-4o-mini`, `allow_delegation: false`, and `verbose: true`.

`src/trading_agents/crews/analyst_crew/config/tasks.yaml` must contain exactly these tasks in order: `market_analysis`, `sentiment_analysis`, `news_analysis`, and `fundamentals_analysis`. Each task has `agent: analyst` and `markdown: true`. The market task includes the allowed indicator names and instructs the model to call `get_stock_data` before `get_indicators`. The sentiment task includes pre-fetched news, StockTwits, and Reddit blocks. The news task describes company-specific and global macro news analysis. The fundamentals task describes company fundamental analysis.

`src/trading_agents/crews/analyst_crew/analyst_crew.py` must define `AnalystCrew` with one `@agent` method named `analyst` and four `@task` methods named exactly like the YAML keys. The `crew()` method must return `Crew(agents=[self.analyst()], tasks=[self.market_analysis(), self.sentiment_analysis(), self.news_analysis(), self.fundamentals_analysis()], process=Process.sequential, tracing=True, verbose=True)`. The helper `run_analyst_stage(inputs)` prepares inputs, kicks off that sequential crew once, and extracts all four task outputs by name.

The helper `prepare_analyst_inputs(inputs)` must accept `ticker` and either `current_date` or the compatibility field `trade_date`. It normalizes the ticker to uppercase, validates required strings, sets `current_date` from `current_date` when supplied and otherwise from `trade_date`, sets `end_date` equal to `current_date`, computes `start_date` and `sentiment_start_date` as seven calendar days before `current_date`, sets `asset_label` from the ticker unless supplied, and ensures `news_block`, `stocktwits_block`, and `reddit_block` exist for the sentiment task. It populates the `trade_date` compatibility alias with the normalized `current_date` and preserves `news_sentiment_block` and `sentiment_start_date` aliases for compatibility with existing flow code and tests, but the YAML prompts do not use `{trade_date}`.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm CrewAI and tools import:

       uv run python -c "import crewai; print(crewai.__version__)"
       uv run python -c "from trading_agents.tools import get_stock_data, get_indicators, get_news, get_global_news, get_fundamentals; print('tools ok')"

   Expected output includes CrewAI `1.14.5` and `tools ok`.

2. Edit these files:

       src/trading_agents/crews/analyst_crew/analyst_crew.py
       src/trading_agents/crews/analyst_crew/config/agents.yaml
       src/trading_agents/crews/analyst_crew/config/tasks.yaml
       tests/test_analyst_crew_config.py

3. Run focused validation:

       uv run pytest tests/test_analyst_crew_config.py

   Observed output on 2026-05-25 after the current-date correction:

       tests/test_analyst_crew_config.py ...........                            [100%]
       11 passed

4. Run the full deterministic suite before considering the implementation complete:

       uv run pytest

   Observed output on 2026-05-25 after the current-date correction:

       24 passed, 10 warnings

## Validation and Acceptance

Acceptance requires all of the following:

- `AnalystCrew().crew()` constructs one agent and four tasks in the order `market_analysis`, `sentiment_analysis`, `news_analysis`, `fundamentals_analysis`.
- `AnalystCrew().analyst().tools` is empty.
- The market task has `get_stock_data` and `get_indicators`.
- The sentiment task has no tools.
- The news task has `get_news` and `get_global_news`.
- The fundamentals task has `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`.
- `run_analyst_stage` returns exactly the four report keys `market_report`, `sentiment_report`, `news_report`, and `fundamentals_report`.
- Mocked tests pass without an LLM key.
- With live credentials and network access, an analyst run for `ticker=NVDA` and `current_date=2024-05-24` or compatibility input `trade_date=2024-05-24` produces four non-empty markdown strings.

## Idempotence and Recovery

The changes are local to the analyst crew, tests, README, and plan documents. Re-running the focused tests is safe. If live execution fails because `OPENAI_API_KEY` is missing or a data provider is unavailable, do not treat that as a deterministic implementation failure; rely on mocked tests and record the live-service issue separately.

If task order or report extraction changes, keep report extraction based on task names first and ordering only as a fallback. This prevents `CrewOutput.raw`, which usually reflects only the final task, from hiding earlier reports.

## Artifacts and Notes

Analyst task source map from `PROMPTS.md`:

- `market_analysis` uses task tools `get_stock_data` and `get_indicators`, chooses up to eight complementary indicators, and writes a detailed market report with a final markdown table.
- `sentiment_analysis` uses no task tools. It analyzes pre-fetched Yahoo Finance news, StockTwits messages, and Reddit posts, and writes a sentiment report with a final markdown table.
- `news_analysis` uses task tools `get_news` and `get_global_news`, and writes a trading-relevant news and macro report with a final markdown table.
- `fundamentals_analysis` uses task tools `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`, and writes a fundamentals report with a final markdown table.

Expected report dictionary:

    {
        "market_report": "<markdown>",
        "sentiment_report": "<markdown>",
        "news_report": "<markdown>",
        "fundamentals_report": "<markdown>"
    }

Validation transcript from 2026-05-25:

    uv run pytest tests/test_analyst_crew_config.py
    tests/test_analyst_crew_config.py ...........                            [100%]
    11 passed, 10 warnings

    uv run pytest
    tests/test_analyst_crew_config.py ...........                            [ 45%]
    tests/test_trading_flow.py ...                                           [ 58%]
    tests/test_trading_tools.py ..........                                   [100%]
    24 passed, 10 warnings

## Interfaces and Dependencies

At the end of this plan, these imports should work:

    from trading_agents.crews.analyst_crew.analyst_crew import AnalystCrew
    from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage

`run_analyst_stage` accepts a dictionary with at least:

    ticker: str
    current_date: str

For compatibility with the current flow, `trade_date` may be supplied instead of `current_date`; the helper maps it to `current_date`. It returns a dictionary with the four report keys named above.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading the README analyst requirements, the current CrewAI scaffold, and the project-local CrewAI skills.
Revision Note: 2026-05-24 01:17Z Implemented the first analyst crew, deterministic tests, and report extraction helper.
Revision Note: 2026-05-24 02:55Z Added `llm: gpt-4o-mini`, explicit dotenv loading, and a live analyst smoke record.
Revision Note: 2026-05-24 06:57Z Recorded tracing behavior and the rejected multi-terminal async task approach.
Revision Note: 2026-05-25 04:53Z Updated the plan and implementation to follow `PROMPTS.md`: one Analyst agent, four sequential tasks, and task-level tools.
Revision Note: 2026-05-25 06:19Z Clarified that analyst YAML uses `{current_date}` rather than `{trade_date}`, made `{end_date}` equal `{current_date}`, and made the past-week start dates automatic.
