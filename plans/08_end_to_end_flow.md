# Wire the End-to-End TradingAgents Flow (Plan 08)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project will run as a CrewAI Flow that accepts a stock ticker and trade date, executes the five TradingAgents stages in order, saves the intermediate artifacts, and returns the final trading result defined by `README.md` and `PROMPTS.md`: the Portfolio Crew's structured `PortfolioDecision`, carrying a final position rating (`Buy` / `Overweight` / `Hold` / `Underweight` / `Sell`) and its supporting thesis.

A user should be able to run the project with a trigger payload such as `{"ticker": "NVDA", "trade_date": "2024-05-24"}` and inspect analyst reports, debate transcripts, the trader plan, the risk debate, and the final portfolio decision.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the required five-stage flow and final output contract.
- [x] (2026-05-23 14:20Z) Read the current `src/trading_agents/main.py`, which still defines a placeholder content-writing flow.
- [x] (2026-05-24 08:12Z) Removed the generated `src/trading_agents/crews/content_crew` reference and replaced `main.py` with a traced analyst-stage `TradingAgentsFlow` so live runs now create CrewAI traces before the full end-to-end implementation.
- [x] (2026-05-23 14:20Z) Read `tests/eval_cases/trading_agent_eval_cases.yaml` and noted the expected evidence categories, risk concerns, and unacceptable failure modes.
- [x] (2026-05-26 00:00Z) Renumbered this file from plan 04 to plan 07 after splitting the former combined decision-stage plan into four crew-specific plans.
- [x] (2026-06-09) Confirmed plans 01, 02, 03, 04, 05, and 06 are implemented (each crew exposes its `run_*_stage` helper).
- [x] (2026-06-09) Extended the analyst-stage `TradingAgentsFlow` into the full end-to-end flow: `prepare_inputs`, `run_analysts`, `run_research`, `run_trader`, `run_risk_management`, `run_portfolio`, and `save_outputs`.
- [x] (2026-06-09) Added output persistence for every stage via `save_outputs`.
- [x] (2026-06-09) Added mocked end-to-end tests in `tests/test_trading_flow.py`.
- [x] (2026-06-11) Split the evaluation out of this plan into `plans/07_evaluation_backtest.md` (the README CR backtest needs a prepared historical dataset, an evaluation execution mode, an exchange simulator, and an orchestration runner — far more than a YAML screen), then renumbered this flow plan from 07 to 08. This plan no longer owns evaluation.
- [ ] Run the final smoke tests and record outputs here.
- [x] (2026-06-09) Applied the runtime conventions from plans 02 through 06: `load_dotenv()` runs before flow execution in `main.py`, `gpt-4o-mini` stays the default agent LLM in crew YAML (the Portfolio Crew's final decision is the one documented exception, which uses the deep LLM), tools are bound at the task level, and tracing is enabled on the flow.

## Surprises & Discoveries

- Observation: The current scripts in `pyproject.toml` already point to `trading_agents.main:kickoff`, `plot`, and `run_with_trigger`, so the flow can be replaced without changing script names.
  Evidence: `[project.scripts]` maps `kickoff`, `run_crew`, `plot`, and `run_with_trigger` to functions in `trading_agents.main`.
- Observation: The repository already has evaluation cases for ticker/date scenarios, but no test runner is present yet.
  Evidence: `tests/eval_cases/trading_agent_eval_cases.yaml` contains cases such as `nvda_2024_05_24`, `tsla_2024_04_24`, and `ba_2024_01_08`.
- Observation: The flow output contract is the Portfolio Crew's structured `PortfolioDecision`, not an `approve`/`reject` gate over the trader plan.
  Evidence: `PROMPTS.md` section 5 and `README.md` ("The output of the flow is the Portfolio Crew's final trade decision: a `PortfolioDecision` carrying the final position rating and its supporting thesis.") define a 5-tier `PortfolioRating`; `schemas.py` defines `PortfolioDecision`, `LessonRecord`, and `LessonBook`; and `main.py` stores `final_trade_decision` and `lessons` as state and persists `final_trade_decision.md`.
- Observation: The Portfolio Crew is the one documented exception to the `gpt-4o-mini` default.
  Evidence: `PROMPTS.md` states "the portfolio manager will use a deep LLM only for making the final decision," and `portfolio_crew.py` selects a deep model for the final decision and a quick model for self-reflection.
- Observation: Plan 02 established runtime conventions that the final flow must preserve.
  Evidence: The analyst stage now loads `.env` explicitly with `load_dotenv()`, sets the shared analyst agent to `llm: gpt-4o-mini`, enables Crew-level tracing, runs analyst tasks sequentially, assigns tools at the task level, and maps the flow compatibility field `trade_date` to the analyst prompt variable `current_date`.
- Observation: CrewAI tracing is a Crew/Flow setting, not a Task setting.
  Evidence: The official CrewAI tracing docs show `Crew(..., tracing=True)` and `Flow(..., tracing=True)`; local CrewAI 1.14.5 exposes `tracing` on `Crew.model_fields` but not on `Task.model_fields`.

## Decision Log

- Decision: Replace `ContentFlow` with `TradingAgentsFlow` in `src/trading_agents/main.py` but keep script function names stable.
  Rationale: The package entry points already target `trading_agents.main`; changing the class and behavior behind those functions is enough and avoids breaking CLI usage.
  Date/Author: 2026-05-23 / Codex
- Decision: Use a structured Pydantic state class for the Flow.
  Rationale: CrewAI flow guidance recommends structured state for production-like workflows, and this pipeline passes many named artifacts between stages.
  Date/Author: 2026-05-23 / Codex
- Decision: Save intermediate outputs under `output/{ticker}_{trade_date}/`.
  Rationale: Users need to inspect how the final decision was reached, and per-run directories prevent overwriting unrelated ticker/date analyses.
  Date/Author: 2026-05-23 / Codex
- Decision: Initialize the final `TradingAgentsFlow` with tracing enabled.
  Rationale: CrewAI tracing belongs on Flow or Crew objects, and the end-to-end orchestration is where cross-stage debugging is most useful.
  Date/Author: 2026-05-24 / Codex
- Decision: Import `load_dotenv` and call `load_dotenv()` in `src/trading_agents/main.py` before live flow execution.
  Rationale: The flow and its stage helpers need `OPENAI_API_KEY` loaded before any CrewAI kickoff, and plan 02 proved explicit dotenv loading works.
  Date/Author: 2026-05-24 / Codex
- Decision: Keep `gpt-4o-mini` as the default LLM by relying on each crew's `agents.yaml`, rather than setting a competing model in the flow.
  Rationale: Model selection is an agent-level CrewAI concern, and keeping it in YAML matches the analyst crew and future decision crew conventions.
  Date/Author: 2026-05-24 / Codex
- Decision: The flow output is the Portfolio Crew's structured `PortfolioDecision`, not a `Hold`-vs-trader-plan string derived from an `approve`/`reject` value.
  Rationale: `PROMPTS.md` section 5 and `README.md` define the Portfolio Manager output as a `PortfolioDecision` with a 5-tier `PortfolioRating` (`Buy` / `Overweight` / `Hold` / `Underweight` / `Sell`) plus its thesis. There is no `approve`/`reject` gate, so the earlier `finalize_result` mapping and `final_output` state field were removed.
  Date/Author: 2026-06-09 / Claude
- Decision: The Portfolio Crew runs self-reflection over prior lesson records before the final decision, and the final decision uses the deep LLM while self-reflection uses the quick LLM.
  Rationale: `PROMPTS.md` section 5 specifies lesson records, benchmark-relative alpha returns, and "the portfolio manager will use a deep LLM only for making the final decision." This is the documented exception to the `gpt-4o-mini` default and lives inside the Portfolio Crew, so the flow only consumes its `final_trade_decision` and `lessons` outputs.
  Date/Author: 2026-06-09 / Claude
- Decision: Persist the final decision as `final_trade_decision.md` and the research transcript as `debate_history.md`; drop the planned `portfolio_decision.txt` and `final_output.md`.
  Rationale: With the output contract being a `PortfolioDecision` rather than an approve/reject string, a dedicated `portfolio_decision.txt` and a separate `final_output.md` are redundant. The implemented `save_outputs` writes one markdown artifact per stage.
  Date/Author: 2026-06-09 / Claude

## Outcomes & Retrospective

The end-to-end `TradingAgentsFlow` is implemented in `src/trading_agents/main.py` with all five stages, per-run persistence via `save_outputs`, and mocked tests in `tests/test_trading_flow.py`. The remaining work is the evaluation runner against `tests/eval_cases/trading_agent_eval_cases.yaml`. The largest plan correction was aligning the output contract with `PROMPTS.md`: the Portfolio Crew now emits a structured `PortfolioDecision` (5-tier rating plus thesis and lesson records), so the earlier `approve`/`reject` → `Hold`/trader-plan mapping and the `final_output` field were dropped. Update this section again after the evaluation runner lands and after a live validation run.

## Context and Orientation

This plan depends on the prior plans:

- `plans/01_foundation_and_market_tools.md` for installability and tools.
- `plans/02_analyst_crew.md` for the four analyst reports.
- `plans/03_research_crew.md` for the research-stage debate and investment plan helper.
- `plans/04_trader_crew.md` for the trader-stage plan helper.
- `plans/05_risk_management_crew.md` for the risk-stage debate helper.
- `plans/06_portfolio_crew.md` for the final portfolio approval helper.

The current `src/trading_agents/main.py` defines `TradingAgentsState`, a traced `TradingAgentsFlow`, and functions `kickoff`, `plot`, `run_with_trigger`, and `cli` (the `analyze` entry point). The flow now runs all five stages end to end and writes one markdown artifact per stage. The remaining work for this plan is the evaluation checks against `tests/eval_cases/trading_agent_eval_cases.yaml`.

Definitions:

The final trade decision is the Portfolio Crew's `PortfolioDecision`: a structured object whose `rating` is exactly one of `Buy` / `Overweight` / `Hold` / `Underweight` / `Sell` (the `PortfolioRating` scale shared with the Research Manager), together with `executive_summary`, `investment_thesis`, and optional `price_target` and `time_horizon`. The final flow output is this `PortfolioDecision`; there is no separate `approve`/`reject` gate and no `Hold`-vs-trader-plan mapping.

## Plan of Work

First, import `load_dotenv` from `dotenv` in `src/trading_agents/main.py` and call `load_dotenv()` before creating or kicking off the flow. The flow implementation must enable tracing with `TradingAgentsFlow(tracing=True)`. Do not add tracing to tasks. Keep `gpt-4o-mini` as the default LLM through each crew's `agents.yaml`; the flow should not override that agent-level setting. The one documented exception lives inside the Portfolio Crew, where the final decision uses the deep LLM and self-reflection uses the quick LLM — that selection is owned by the Portfolio Crew, not the flow.

Then, define a `TradingAgentsState` Pydantic model in `src/trading_agents/main.py`. The structured stage outputs (`investment_plan`, `trader_plan`, `final_trade_decision`) are dictionaries serialized from their Pydantic models, and `lessons` is the list of lesson records returned by the Portfolio Crew. It should include at least:

    ticker: str = "NVDA"
    trade_date: str = "2024-05-24"
    fundamentals_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    market_report: str = ""
    debate_history: str = ""
    investment_plan: dict[str, Any] = {}
    trader_plan: dict[str, Any] = {}
    risk_debate_history: str = ""
    final_trade_decision: dict[str, Any] = {}
    lessons: list[dict[str, Any]] = []
    output_dir: str = ""

Second, define `TradingAgentsFlow(Flow[TradingAgentsState])`. Keep the flow stages readable and one-purpose:

1. `prepare_inputs`: a `@start()` method that reads `ticker` and `trade_date` from `crewai_trigger_payload` when present, validates the date format, normalizes ticker to upper-case, and sets `output_dir`.
2. `run_analysts`: a `@listen(prepare_inputs)` method that calls `run_analyst_stage` and writes the four reports into state. The flow may keep accepting `trade_date`, but the analyst stage maps it to `current_date` for YAML prompt interpolation.
3. `run_research`: calls `run_research_stage` and writes `debate_history` and the structured `investment_plan`.
4. `run_trader`: calls `run_trader_stage` and writes the structured `trader_plan`.
5. `run_risk_management`: calls `run_risk_stage` and writes `risk_debate_history`.
6. `run_portfolio`: calls `run_portfolio_stage` (which performs lesson-record updates, self-reflection with the quick LLM, and the final decision with the deep LLM) and writes the structured `final_trade_decision` and the `lessons` list.
7. `save_outputs`: writes one markdown artifact per stage to `output_dir`, prints the output path, and returns the serialized flow state. There is no `approve`/`reject` mapping — the final flow output is the `PortfolioDecision` itself.

Third, update the script functions:

- `kickoff()` should create `TradingAgentsFlow(tracing=True)` and call `kickoff` with default inputs or no inputs.
- `plot()` should plot `TradingAgentsFlow`.
- `run_with_trigger()` should keep accepting one JSON command-line argument, validate it, and pass it as `crewai_trigger_payload`.
- `cli()` (the `analyze` entry point) should accept `--ticker` and `--trade-date`, build a payload, and kick off the flow, defaulting the trade date to the current UTC date.

Fourth, add persistence helpers. Create a `save_outputs(state: TradingAgentsState)` function that writes one markdown artifact per stage:

    output/{ticker}_{trade_date}/fundamentals_report.md
    output/{ticker}_{trade_date}/sentiment_report.md
    output/{ticker}_{trade_date}/news_report.md
    output/{ticker}_{trade_date}/market_report.md
    output/{ticker}_{trade_date}/debate_history.md
    output/{ticker}_{trade_date}/investment_plan.md
    output/{ticker}_{trade_date}/trader_plan.md
    output/{ticker}_{trade_date}/risk_debate_history.md
    output/{ticker}_{trade_date}/final_trade_decision.md

The structured artifacts (`investment_plan.md`, `trader_plan.md`, `final_trade_decision.md`) are rendered from their dict state fields. Writes should be idempotent and replace only files for the same ticker/date run.

Fifth, add mocked end-to-end tests. Mock the stage helper functions to avoid LLM and network calls. Test at least:

- Trigger payload sets ticker/date.
- The flow threads each stage's output into the next stage's inputs (reports → research → trader → risk → portfolio).
- A mocked `PortfolioDecision` (e.g. rating `Buy`) is written to `final_trade_decision` state and persisted to `final_trade_decision.md`.
- Missing ticker defaults to `NVDA` or a documented default.
- Invalid date raises a clear error before any crew runs.

Evaluation is no longer part of this plan. The README's cumulative-return backtest (AAPL/GOOGL/AMZN over 2024-Q1) requires a prepared historical dataset, an evaluation execution mode, an exchange simulator, and an orchestration runner, which are specified separately in `plans/07_evaluation_backtest.md`. The qualitative `tests/eval_cases/trading_agent_eval_cases.yaml` screen is orthogonal to the CR backtest and is left for a possible future plan.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm prior stage helpers import:

       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage; from trading_agents.crews.research_crew.research_crew import run_research_stage; from trading_agents.crews.trader_crew.trader_crew import run_trader_stage; from trading_agents.crews.risk_management_crew.risk_management_crew import run_risk_stage; from trading_agents.crews.portfolio_crew.portfolio_crew import run_portfolio_stage; print('stages ok')"

   Expected output:

       stages ok

2. Edit `src/trading_agents/main.py` to replace content-specific classes and imports with the trading flow.

3. Add tests, for example:

       tests/test_trading_flow.py

4. Run mocked flow tests:

       uv run pytest tests/test_trading_flow.py

   Expected success:

       passed

5. (Evaluation moved to plan 07 — see `plans/07_evaluation_backtest.md`.)

6. Run a no-live-services smoke test with mocked stage helpers, if provided:

       uv run python -m trading_agents.dev_smoke_flow

   Expected output shape:

       Final rating: Buy
       Output directory: output/NVDA_2024-05-24

7. Before a live run, confirm `.env` loads the OpenAI key:

       uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('OPENAI_API_KEY set' if os.getenv('OPENAI_API_KEY') else 'OPENAI_API_KEY missing')"

   Expected output:

       OPENAI_API_KEY set

8. With valid `OPENAI_API_KEY` and network access, run the actual flow:

       uv run run_with_trigger '{"ticker":"NVDA","trade_date":"2024-05-24"}'

   Expected behavior:

   - The console shows the five stages running in order.
   - `output/NVDA_2024-05-24/` is created.
   - `final_trade_decision.md` contains a `PortfolioDecision` whose rating is one of `Buy` / `Overweight` / `Hold` / `Underweight` / `Sell`.
   - The command returns or prints the final flow output, which is the `PortfolioDecision`.

## Validation and Acceptance

Acceptance requires:

- `src/trading_agents/main.py` no longer runs the placeholder content crew.
- The flow accepts trigger payload JSON with `ticker` and `trade_date`.
- The flow stores all intermediate artifacts in a per-run output directory.
- Mocked tests prove the structured `PortfolioDecision` is produced, threaded into state, and persisted.
- A live run with credentials can execute the full sequence without changing code.

Evaluation (the README cumulative-return backtest) is specified and accepted separately in `plans/07_evaluation_backtest.md`.

The end-to-end mocked tests should fail before this plan is implemented because `TradingAgentsFlow` and the stage helpers do not yet exist. They should pass after implementation.

## Idempotence and Recovery

Running the same ticker/date flow more than once should overwrite only files in `output/{ticker}_{trade_date}/`. It should not delete other output directories.

If a stage fails, preserve outputs from prior completed stages and raise a clear exception naming the failed stage. Do not silently continue to later stages with empty reports.

If `run_with_trigger()` receives invalid JSON, raise the existing clear error style: `Invalid JSON payload provided as argument`. If `trade_date` is invalid, raise a clear `ValueError` such as `trade_date must use YYYY-MM-DD format.`.

If live LLM credentials are missing, mocked tests remain the source of local acceptance. Record live credential failures in `Surprises & Discoveries` rather than weakening tests.

## Artifacts and Notes

The flow contract from `README.md` and `PROMPTS.md` is:

    Analyst Crew
    Research Crew
    Trader Crew
    Risk Management Crew
    Portfolio Crew

    final output = Portfolio Crew's PortfolioDecision
                   (rating in {Buy, Overweight, Hold, Underweight, Sell}
                    plus executive_summary, investment_thesis, and optional
                    price_target and time_horizon)

Example trigger payload:

    {"ticker":"NVDA","trade_date":"2024-05-24"}

Example output directory:

    output/NVDA_2024-05-24/

Evaluation cases currently include these tickers and dates:

    NVDA 2024-05-24
    TSLA 2024-04-24
    AAPL 2024-06-11
    GME 2024-05-14
    BA 2024-01-08
    PFE 2023-12-13
    JPM 2023-03-13
    XOM 2022-03-08
    META 2022-10-27
    MSFT 2024-07-31

## Interfaces and Dependencies

At the end of this plan, these commands should work:

    uv run python -c "from trading_agents.main import TradingAgentsFlow; print(TradingAgentsFlow)"
    uv run run_with_trigger '{"ticker":"NVDA","trade_date":"2024-05-24"}'
    uv run pytest tests/test_trading_flow.py

The main flow should import only stage helper functions, not individual agent internals. This keeps `main.py` responsible for orchestration and each crew responsible for its own prompts, tasks, and implementation details.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading the README flow contract, current placeholder `main.py`, CrewAI flow guidance, and the available evaluation cases. This plan intentionally makes mocked validation mandatory before live LLM execution.

Revision Note: 2026-05-24 06:57Z Added plan 02 runtime conventions to the unimplemented end-to-end flow: explicit dotenv loading before live runs, preserve `gpt-4o-mini` in crew YAML as the default LLM, and enable tracing on Flow/Crew objects rather than Task objects.


Revision Note: 2026-05-26 renumbered this file from plan 04 to plan 07 after splitting the former combined decision-stage plan into four crew-specific plans for sequential implementation.

Revision Note: 2026-06-11 split the evaluation out of this plan into `plans/07_evaluation_backtest.md` and pushed back this plan's evaluation scope, then renumbered this flow plan from 07 to 08 (renamed `plans/08_end_to_end_flow.md`) so the next-to-implement evaluation carries the active plan number 07. After adding the README `# Evaluation` section, it became clear the cumulative-return backtest (AAPL/GOOGL/AMZN over 2024-Q1) needs a prepared historical dataset (several analyst data sources cannot be queried for a past window), an evaluation execution mode, an exchange simulator, and an orchestration runner — far beyond the single "evaluation checks" bullet this plan carried. This plan now owns only the end-to-end flow; the open evaluation checklist item, the "Sixth, add an evaluation runner …" paragraph, and the `tests/test_eval_cases.py` references were removed and replaced with pointers to plan 07. The qualitative `tests/eval_cases/trading_agent_eval_cases.yaml` screen is orthogonal to the CR backtest and remains unowned.

Revision Note: 2026-06-09 aligned this plan with `PROMPTS.md` (the latest source of truth). Replaced the stale `approve`/`reject` → `Hold`/trader-plan output contract with the Portfolio Crew's structured `PortfolioDecision` (5-tier `PortfolioRating` plus thesis and lesson records); updated the `TradingAgentsState` fields to the implemented dict/list shapes (added `debate_history` and `lessons`, removed `final_output`); renamed the final flow step from `finalize_result` to `save_outputs`; corrected the persisted artifact list (`debate_history.md`, `final_trade_decision.md`; dropped `portfolio_decision.txt` and `final_output.md`); documented the Portfolio Crew's deep-LLM final decision / quick-LLM self-reflection as the one exception to the `gpt-4o-mini` default; and marked the now-implemented Progress items. Remaining open item: the evaluation runner against `tests/eval_cases/trading_agent_eval_cases.yaml`.
