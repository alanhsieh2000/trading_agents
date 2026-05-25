# Wire the End-to-End TradingAgents Flow and Evaluation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project will run as a CrewAI Flow that accepts a stock ticker and trade date, executes the five TradingAgents stages in order, saves the intermediate artifacts, and returns the final trading result defined by `README.md`: `Hold` when the Portfolio Crew rejects the proposal, otherwise the Trader Crew's plan.

A user should be able to run the project with a trigger payload such as `{"ticker": "NVDA", "trade_date": "2024-05-24"}` and inspect analyst reports, debate transcripts, the trader plan, the risk debate, the portfolio decision, and the final output.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the required five-stage flow and final output contract.
- [x] (2026-05-23 14:20Z) Read the current `src/trading_agents/main.py`, which still defines a placeholder content-writing flow.
- [x] (2026-05-24 08:12Z) Removed the generated `src/trading_agents/crews/content_crew` reference and replaced `main.py` with a traced analyst-stage `TradingAgentsFlow` so live runs now create CrewAI traces before the full plan 04 implementation.
- [x] (2026-05-23 14:20Z) Read `tests/eval_cases/trading_agent_eval_cases.yaml` and noted the expected evidence categories, risk concerns, and unacceptable failure modes.
- [ ] Ensure plans 01, 02, and 03 have been implemented.
- [ ] Extend the current analyst-stage `TradingAgentsFlow` into the full end-to-end TradingAgents flow.
- [ ] Add output persistence for every stage.
- [ ] Add mocked end-to-end tests.
- [ ] Add evaluation checks using `tests/eval_cases/trading_agent_eval_cases.yaml`.
- [ ] Run the final smoke tests and record outputs here.
- [ ] Apply the runtime conventions proven in plan 02 and required by plan 03: load `.env` with `load_dotenv()` before live execution, preserve `gpt-4o-mini` as the default agent LLM in crew YAML, use task-level tools when one agent performs tool-specific tasks, and enable tracing on the flow and every crew invocation.

## Surprises & Discoveries

- Observation: The current scripts in `pyproject.toml` already point to `trading_agents.main:kickoff`, `plot`, and `run_with_trigger`, so the flow can be replaced without changing script names.
  Evidence: `[project.scripts]` maps `kickoff`, `run_crew`, `plot`, and `run_with_trigger` to functions in `trading_agents.main`.
- Observation: The repository already has evaluation cases for ticker/date scenarios, but no test runner is present yet.
  Evidence: `tests/eval_cases/trading_agent_eval_cases.yaml` contains cases such as `nvda_2024_05_24`, `tsla_2024_04_24`, and `ba_2024_01_08`.
- Observation: The flow output contract is intentionally narrower than the internal decision artifacts.
  Evidence: README says the Flow output is `Hold` if the Portfolio Crew rejects, otherwise the Trader Crew output.
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

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a runnable end-to-end TradingAgents Flow with mocked tests and evaluation-case checks. Update this section after implementation and after validation runs.

## Context and Orientation

This plan depends on the prior plans:

- `plans/01_foundation_and_market_tools.md` for installability and tools.
- `plans/02_analyst_crew.md` for the four analyst reports.
- `plans/03_debate_trader_risk_and_portfolio_crews.md` for research, trader, risk, and portfolio stage helpers.

The current `src/trading_agents/main.py` defines `TradingAgentsState`, a traced `TradingAgentsFlow`, and functions `kickoff`, `plot`, and `run_with_trigger`. The interim flow runs the implemented analyst stage and writes four analyst report artifacts. Plan 04 still needs to extend this flow with research, trader, risk, portfolio, final output mapping, and evaluation checks.

Definitions:

The final trade decision is the Portfolio Crew's exact `approve` or `reject` value. The final flow output is different: it is `Hold` when the final trade decision is `reject`, otherwise it is the Trader Crew plan.

## Plan of Work

First, import `load_dotenv` from `dotenv` in `src/trading_agents/main.py` and call `load_dotenv()` before creating or kicking off the flow. The flow implementation must enable tracing with `TradingAgentsFlow(tracing=True)` or an equivalent `super().__init__(tracing=True)` pattern. Do not add tracing to tasks. Keep `gpt-4o-mini` as the default LLM through each crew's `agents.yaml`; the flow should not override that agent-level setting unless the user explicitly requests a model change.

Then, define a `TradingAgentsState` Pydantic model in `src/trading_agents/main.py` or import it from `src/trading_agents/schemas.py`. It should include at least:

    ticker: str = "NVDA"
    trade_date: str = "2024-05-24"
    fundamentals_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    market_report: str = ""
    investment_plan: str = ""
    trader_plan: str = ""
    risk_debate_history: str = ""
    final_trade_decision: str = ""
    final_output: str = ""
    output_dir: str = ""

Second, define `TradingAgentsFlow(Flow[TradingAgentsState])`. Keep the flow stages readable and one-purpose:

1. `prepare_inputs`: a `@start()` method that reads `ticker` and `trade_date` from `crewai_trigger_payload` when present, validates the date format, normalizes ticker to upper-case, and sets `output_dir`.
2. `run_analysts`: a `@listen(prepare_inputs)` method that calls `run_analyst_stage` and writes the four reports into state. The flow may keep accepting `trade_date`, but the analyst stage maps it to `current_date` for YAML prompt interpolation.
3. `run_research`: calls `run_research_stage` and writes `investment_plan`.
4. `run_trader`: calls `run_trader_stage` and writes `trader_plan`.
5. `run_risk_management`: calls `run_risk_stage` and writes `risk_debate_history`.
6. `run_portfolio`: calls `run_portfolio_stage` and writes `final_trade_decision`.
7. `finalize_result`: maps `reject` to `Hold`, maps `approve` to `self.state.trader_plan`, writes artifacts to disk, prints the output path, and returns `self.state.final_output`.

Third, update the script functions:

- `kickoff()` should create `TradingAgentsFlow()` and call `kickoff` with default inputs or no inputs.
- `plot()` should plot `TradingAgentsFlow`.
- `run_with_trigger()` should keep accepting one JSON command-line argument, validate it, and pass it as `crewai_trigger_payload`.

Fourth, add persistence helpers. Create a function such as `save_stage_outputs(state: TradingAgentsState)` that writes:

    output/{ticker}_{trade_date}/fundamentals_report.md
    output/{ticker}_{trade_date}/sentiment_report.md
    output/{ticker}_{trade_date}/news_report.md
    output/{ticker}_{trade_date}/market_report.md
    output/{ticker}_{trade_date}/investment_plan.md
    output/{ticker}_{trade_date}/trader_plan.md
    output/{ticker}_{trade_date}/risk_debate_history.md
    output/{ticker}_{trade_date}/portfolio_decision.txt
    output/{ticker}_{trade_date}/final_output.md

Writes should be idempotent and replace only files for the same ticker/date run.

Fifth, add mocked end-to-end tests. Mock the stage helper functions to avoid LLM and network calls. Test at least:

- Trigger payload sets ticker/date.
- `reject` produces final output `Hold`.
- `approve` produces final output equal to the mocked trader plan.
- Missing ticker defaults to `NVDA` or a documented default.
- Invalid date raises a clear error before any crew runs.

Sixth, add an evaluation runner that reads `tests/eval_cases/trading_agent_eval_cases.yaml`. The first version can be lightweight and deterministic: it should run a mocked or live flow result through checks that flag missing expected evidence category terms, missing expected risk concern terms, and unacceptable failure mode phrases. Place the runner under `src/trading_agents/evaluation.py` or `tests/test_eval_cases.py`. Do not claim this replaces human financial review; it is a regression screen.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm prior stage helpers import:

       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage; from trading_agents.crews.research_crew.research_crew import run_research_stage; from trading_agents.crews.trader_crew.trader_crew import run_trader_stage; from trading_agents.crews.risk_management_crew.risk_management_crew import run_risk_stage; from trading_agents.crews.portfolio_crew.portfolio_crew import run_portfolio_stage; print('stages ok')"

   Expected output:

       stages ok

2. Edit `src/trading_agents/main.py` to replace content-specific classes and imports with the trading flow.

3. Add tests, for example:

       tests/test_trading_flow.py
       tests/test_eval_cases.py

4. Run mocked flow tests:

       uv run pytest tests/test_trading_flow.py

   Expected success:

       passed

5. Run evaluation-case tests:

       uv run pytest tests/test_eval_cases.py

   Expected success after implementation:

       passed

6. Run a no-live-services smoke test with mocked stage helpers, if provided:

       uv run python -m trading_agents.dev_smoke_flow

   Expected output shape:

       Final decision: reject
       Final output: Hold
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
   - `portfolio_decision.txt` contains `approve` or `reject`.
   - The command returns or prints the final flow output, which is `Hold` for reject or the trader plan for approve.

## Validation and Acceptance

Acceptance requires:

- `src/trading_agents/main.py` no longer runs the placeholder content crew.
- The flow accepts trigger payload JSON with `ticker` and `trade_date`.
- The flow stores all intermediate artifacts in a per-run output directory.
- Mocked tests prove the final output mapping for both `approve` and `reject`.
- Evaluation tests read `tests/eval_cases/trading_agent_eval_cases.yaml` and fail clearly when expected evidence or risk concerns are missing from a candidate output.
- A live run with credentials can execute the full sequence without changing code.

The end-to-end mocked tests should fail before this plan is implemented because `TradingAgentsFlow` and the stage helpers do not yet exist. They should pass after implementation.

## Idempotence and Recovery

Running the same ticker/date flow more than once should overwrite only files in `output/{ticker}_{trade_date}/`. It should not delete other output directories.

If a stage fails, preserve outputs from prior completed stages and raise a clear exception naming the failed stage. Do not silently continue to later stages with empty reports.

If `run_with_trigger()` receives invalid JSON, raise the existing clear error style: `Invalid JSON payload provided as argument`. If `trade_date` is invalid, raise a clear `ValueError` such as `trade_date must be YYYY-MM-DD`.

If live LLM credentials are missing, mocked tests remain the source of local acceptance. Record live credential failures in `Surprises & Discoveries` rather than weakening tests.

## Artifacts and Notes

The flow contract from `README.md` is:

    Analyst Crew
    Research Crew
    Trader Crew
    Risk Management Crew
    Portfolio Crew

    If final trade decision is reject:
        final output = "Hold"
    If final trade decision is approve:
        final output = trader plan

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
    uv run pytest tests/test_trading_flow.py tests/test_eval_cases.py

The main flow should import only stage helper functions, not individual agent internals. This keeps `main.py` responsible for orchestration and each crew responsible for its own prompts, tasks, and implementation details.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading the README flow contract, current placeholder `main.py`, CrewAI flow guidance, and the available evaluation cases. This plan intentionally makes mocked validation mandatory before live LLM execution.

Revision Note: 2026-05-24 06:57Z Added plan 02 runtime conventions to the unimplemented end-to-end flow: explicit dotenv loading before live runs, preserve `gpt-4o-mini` in crew YAML as the default LLM, and enable tracing on Flow/Crew objects rather than Task objects.
