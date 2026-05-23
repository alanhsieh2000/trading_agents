# Implement the Analyst Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project will have a CrewAI Analyst Crew that produces four separate reports for a ticker and date: fundamentals, sentiment, news, and market analysis. A user should be able to run the analyst stage and inspect four evidence-backed markdown reports before any debate or trading decision happens.

This is the first user-visible TradingAgents stage. It turns raw data into specialized analysis that later crews can debate.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the required Analyst Team roles, task outputs, and upstream TradingAgents source URLs.
- [x] (2026-05-23 14:20Z) Read the reference `content_crew` scaffold and CrewAI skills for YAML, `@CrewBase`, agents, tasks, tools, and async tasks.
- [x] (2026-05-23 14:20Z) Identified the required analyst tool names and report outputs.
- [ ] Ensure `plans/01_foundation_and_market_tools.md` has been completed or has compatible tool exports.
- [ ] Create `src/trading_agents/crews/analyst_crew/` with CrewAI class and YAML configuration.
- [ ] Add focused tests for config keys, tool wiring, and report extraction.
- [ ] Run a mocked analyst-stage smoke test and record the output here.

## Surprises & Discoveries

- Observation: The project currently contains only `content_crew`, and `README.md` says that crew is a reference, not part of the trading implementation.
  Evidence: `README.md` explicitly says `src/trading_agents/crews/content_crew` serves as reference only.
- Observation: The sentiment analyst in the current upstream TradingAgents design avoids tool-calling and injects news, StockTwits, and Reddit blocks directly into the prompt.
  Evidence: The upstream sentiment analyst source prefetches all three blocks before invoking the LLM, while the other analysts bind tools.
- Observation: CrewAI task configuration supports `async_execution`; use it only after tests prove task outputs are still recoverable by name.
  Evidence: The project-local `design-task` skill describes `async_execution=True` for parallel tasks and `context` for downstream waits.

## Decision Log

- Decision: Keep the `content_crew` files as a reference while adding a new `analyst_crew`.
  Rationale: `README.md` says `content_crew` is a reference for implementation expectations. Removing it would erase useful scaffold context.
  Date/Author: 2026-05-23 / Codex
- Decision: Use four separate analyst agents because this split is intrinsic to the TradingAgents architecture, even though CrewAI guidance recommends minimizing agents by default.
  Rationale: Each analyst has a different perspective, evidence type, output contract, and tool surface. This satisfies the `design-agent` criterion for separate agents.
  Date/Author: 2026-05-23 / Codex
- Decision: Implement sentiment as prompt-injected data rather than giving it social-media search tools.
  Rationale: The upstream TradingAgents sentiment analyst was redesigned to reduce fabricated social-media claims by prefetching data before LLM invocation.
  Date/Author: 2026-05-23 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is an Analyst Crew that returns four named report strings and can be validated with mocked tool outputs before live LLM execution. Update this section after implementation and after each validation run.

## Context and Orientation

The project root is `/app/trading_agents`. This plan depends on the tool exports described in `plans/01_foundation_and_market_tools.md`. If that plan is not implemented, complete its dependency and tool milestones first.

Create a new directory:

    src/trading_agents/crews/analyst_crew/
    src/trading_agents/crews/analyst_crew/config/

The new crew should mirror the reference shape in:

    src/trading_agents/crews/content_crew/content_crew.py
    src/trading_agents/crews/content_crew/config/agents.yaml
    src/trading_agents/crews/content_crew/config/tasks.yaml

Important terms:

An analyst report is a markdown string that summarizes one evidence category for the same ticker and trade date. A ticker is the exchange symbol such as `NVDA`. A trade date is the analysis date in `YYYY-MM-DD` format. Technical indicators are mathematical features derived from price and volume history, such as RSI, MACD, Bollinger Bands, ATR, and moving averages.

## Plan of Work

Add `src/trading_agents/crews/analyst_crew/analyst_crew.py` with a `@CrewBase` class named `AnalystCrew`. Use `agents_config = "config/agents.yaml"` and `tasks_config = "config/tasks.yaml"`. Define four `@agent` methods and four `@task` methods. Method names must exactly match the YAML keys.

Use these agent keys:

- `fundamentals_analyst`
- `sentiment_analyst`
- `news_analyst`
- `market_analyst`

Use these task keys:

- `fundamentals_analysis`
- `sentiment_analysis`
- `news_analysis`
- `market_analysis`

Wire tools as follows:

- `fundamentals_analyst` gets `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`.
- `news_analyst` gets `get_news` and `get_global_news`.
- `market_analyst` gets `get_stock_data` and `get_indicators`.
- `sentiment_analyst` gets no CrewAI tools by default. Its task prompt receives `{news_sentiment_block}`, `{stocktwits_block}`, and `{reddit_block}` from flow input or a helper function before kickoff.

In `config/agents.yaml`, adapt role, goal, and backstory from the original TradingAgents agent source files named in `README.md`. Keep the behavior close to the original, but express it in CrewAI YAML terms. The agent definitions must make these responsibilities clear:

- Fundamentals Analyst: researches company fundamentals over the past week, including financial documents, profile, basic financials, and financial history.
- Sentiment Analyst: assesses market sentiment from news headlines, StockTwits messages, and Reddit posts without inventing missing social-media evidence.
- News Analyst: evaluates recent company-specific and macroeconomic news relevant to trading.
- Market Analyst: analyzes price action and technical indicators.

In `config/tasks.yaml`, make each task single-purpose and give an exact expected output:

- `fundamentals_analysis` outputs `fundamentals report`.
- `sentiment_analysis` outputs `sentiment report`.
- `news_analysis` outputs `news report`.
- `market_analysis` outputs `market report`.

Each report should end with a markdown table of key signals. Each task description should include `{ticker}` and `{trade_date}` placeholders. Use `{asset_type}` only if the implementation supports assets beyond stocks; otherwise default to stock and document that limitation.

For market analysis, include the allowed indicator list in the task description so the agent calls exact names:

    close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr, vwma

The market task must instruct the agent to call `get_stock_data` before `get_indicators`. The indicator tool should still be robust if called directly, but the prompt should preserve the original workflow.

Implement a small runner function or method that returns all four task outputs by name. Do not rely only on `CrewOutput.raw`, because that usually represents the final task. Use `result.tasks_output` and task names or ordering to build:

    {
        "fundamentals_report": "...",
        "sentiment_report": "...",
        "news_report": "...",
        "market_report": "..."
    }

If `async_execution=True` is used for parallel analyst tasks, add a prototype test proving `tasks_output` contains all four reports. If async behavior is unstable, keep a sequential CrewAI process for correctness first and record the tradeoff in the Decision Log. The end-to-end flow can later parallelize by launching separate analyst calls once correctness is established.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the dependency and tool foundation is ready:

       uv run python -c "from trading_agents.tools import get_stock_data, get_indicators, get_news, get_global_news, get_fundamentals; print('tools ok')"

   Expected output:

       tools ok

2. Create the analyst crew directory and files:

       src/trading_agents/crews/analyst_crew/analyst_crew.py
       src/trading_agents/crews/analyst_crew/config/agents.yaml
       src/trading_agents/crews/analyst_crew/config/tasks.yaml

3. Implement the `AnalystCrew` class using the reference `ContentCrew` import pattern:

       from crewai import Agent, Crew, Process, Task
       from crewai.project import CrewBase, agent, crew, task

   Include `# type: ignore[index]` on config dictionary access, matching `AGENTS.md`.

4. Add tests, for example `tests/test_analyst_crew_config.py`, that verify:

   - All four YAML agent keys exist.
   - All four YAML task keys exist.
   - Each task's `agent` field names an agent in the same `agents.yaml`.
   - Analyst crew imports without constructing live LLM calls.
   - The tool-bearing agents receive the expected tool names.

5. Add a mocked smoke test that replaces LLM execution or CrewAI kickoff with deterministic outputs and proves the report-extraction helper returns all four report keys.

6. Run:

       uv run pytest tests/test_analyst_crew_config.py

   Expected success:

       passed

7. With valid `OPENAI_API_KEY` and network access, run a live smoke test only after mocked tests pass:

       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage; print(run_analyst_stage({'ticker': 'NVDA', 'trade_date': '2024-05-24'}).keys())"

   Expected output shape:

       dict_keys(['fundamentals_report', 'sentiment_report', 'news_report', 'market_report'])

## Validation and Acceptance

Acceptance requires all of the following:

- The analyst crew imports from `trading_agents.crews.analyst_crew.analyst_crew`.
- The YAML files have matching method, task, and agent keys.
- Mocked tests pass without an LLM key.
- A report-extraction helper returns exactly these keys: `fundamentals_report`, `sentiment_report`, `news_report`, `market_report`.
- With live credentials, an analyst run for `ticker=NVDA` and `trade_date=2024-05-24` produces four non-empty markdown strings, each with a final table.

The new tests should fail before this plan is implemented because `analyst_crew` does not exist, and pass after implementation.

## Idempotence and Recovery

Creating `analyst_crew` is additive. If a test run fails halfway, leave the new files in place and repair the failing key, prompt, or tool import. Do not modify or delete `content_crew`; it is a reference.

If the live smoke test fails because of missing `OPENAI_API_KEY`, do not treat that as implementation failure. Record the missing key and rely on mocked tests for local validation.

If async execution causes missing or reordered task outputs, turn off async execution, record the decision, and keep correctness. Parallelism can be reintroduced after an isolated CrewAI async prototype proves stable.

## Artifacts and Notes

Analyst prompt source map:

- `fundamentals_analyst.py`: comprehensive fundamental information; tools are `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`; output includes a markdown table.
- `sentiment_analyst.py`: prefetches Yahoo Finance news, StockTwits messages, and Reddit posts for the past seven days; output includes overall sentiment, source breakdown, divergences, catalysts, risks, and a markdown table.
- `news_analyst.py`: uses `get_news` and `get_global_news`; output covers recent relevant news and macroeconomic trends with a markdown table.
- `market_analyst.py`: uses `get_stock_data` and `get_indicators`; chooses up to eight complementary indicators from the allowed list and writes a detailed technical report with a markdown table.

Expected report dictionary:

    {
        "fundamentals_report": "<markdown>",
        "sentiment_report": "<markdown>",
        "news_report": "<markdown>",
        "market_report": "<markdown>"
    }

## Interfaces and Dependencies

At the end of this plan, these imports should work:

    from trading_agents.crews.analyst_crew.analyst_crew import AnalystCrew
    from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage

`run_analyst_stage` should accept a dictionary with at least:

    ticker: str
    trade_date: str

It should return a dictionary with the four report keys named above. If the implementation prefers a Pydantic model, define it in `src/trading_agents/schemas.py` and make the helper return either the model or `model_dump()` consistently. Document the choice here when implemented.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading the README analyst requirements, the current CrewAI scaffold, and the project-local CrewAI skills. This plan isolates analyst report generation before debate and flow orchestration.
