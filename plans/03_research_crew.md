# Implement the Research Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can turn the four analyst reports into a structured investment debate and a research-stage investment plan. A user should be able to inspect a bull argument, a bear argument, the debate history built from both, and the final research manager decision before any trader, risk, or portfolio logic runs.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Research Crew before starting the Trader Crew.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Research Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream TradingAgents source summaries for bull researcher, bear researcher, and research manager behavior.
- [x] (2026-05-23 14:20Z) Read CrewAI guidance already used in plan 02 for YAML-backed crews, sequential execution, task-level integration, and traced runs.
- [x] (2026-05-26 06:02Z) Confirmed the analyst stage exposes the four consumed outputs: market_report, sentiment_report, news_report, and fundamentals_report, based on the implemented extraction map and the passing analyst-stage contract tests.
- [x] (2026-05-26 05:51Z) Added the shared research-stage schema and implemented the stage helper.
- [x] (2026-05-26 05:51Z) Implemented the research crew with prompts, debate-history handling, and manager synthesis.
- [x] (2026-05-26 05:51Z) Added mocked config and contract tests for the research stage.
- [x] (2026-05-26 05:51Z) Ran the focused research-stage pytest suite and recorded 9 passing tests.
- [x] (2026-05-26 05:51Z) Preserved the runtime conventions from plan 02: dotenv loading, gpt-4o-mini YAML defaults, and traced crew execution.
- [x] (2026-06-05) Replaced the research prompts with the `PROMPTS.md` Research Team wording and removed the explicit `HAS_MORE` trailer contract.
- [x] (2026-06-05) Updated the research loop so debate length is controlled only by `max_rounds`.
- [x] (2026-06-05) Moved research debate round tuning to `research_stage.max_rounds` in runtime settings.
- [x] (2026-06-05) Wired the Research Crew into `TradingAgentsFlow` after the analyst stage and persisted research outputs under the run output directory.
- [x] (2026-06-05) Set the default research debate length to one round.

## Surprises & Discoveries

- Observation: The README requires iterative debate rounds, while CrewAI tasks remain easiest to reason about as fixed units.
  Evidence: The analyst crew in `src/trading_agents/crews/analyst_crew/analyst_crew.py` uses a fixed sequential crew successfully; iterative behavior will need to live in a Python stage helper rather than in dynamic task construction.
- Observation: The upstream research manager uses a five-level investment rating instead of a binary output.
  Evidence: The earlier combined plan captured the rating scale `Buy`, `Overweight`, `Hold`, `Underweight`, `Sell`; that richer output belongs in the research stage and should not be flattened prematurely.
- Observation: Plan 02 already established working repository conventions for dotenv loading and tracing.
  Evidence: `src/trading_agents/crews/analyst_crew/analyst_crew.py` calls `load_dotenv()` and returns `Crew(..., tracing=True, verbose=True)`.
- Observation: CrewAI 1.14.5 in this repository matches the latest PyPI release, and task-level structured output is stable enough for the research manager contract.
  Evidence: The local version check returned 1.14.5, PyPI reported 1.14.5 as current, and the config test asserts structured output on the manager task.
- Observation: The remaining unchecked plan item was satisfied by analyst-stage contract verification rather than by a new live run.
  Evidence: `uv run pytest tests/test_analyst_crew_config.py -q` passed with 13 tests, including assertions that `run_analyst_stage` returns `market_report`, `sentiment_report`, `news_report`, and `fundamentals_report`.

## Decision Log

- Decision: Split the former combined decision-stage plan into one plan per crew.
  Rationale: The user wants research, trader, risk, and portfolio work implemented and validated sequentially rather than in one large batch.
  Date/Author: 2026-05-26 / Codex
- Decision: Add the first shared schema in this plan by creating `InvestmentPlan` in `src/trading_agents/schemas.py`.
  Rationale: The Research Crew is the first stage that emits structured data consumed by later crews, so the shared schema should begin here.
  Date/Author: 2026-05-26 / Codex
- Decision: Do not ask bull or bear researchers for an explicit stop trailer.
  Rationale: Each researcher should provide a complete argument for the current turn, using history and the other side's latest response; the debate ends when `max_rounds` is reached.
  Date/Author: 2026-06-05 / Codex
- Decision: Keep `gpt-4o-mini` as the YAML default and enable `tracing=True` on the crew.
  Rationale: This matches the already-implemented analyst stage and avoids introducing a second runtime pattern.
  Date/Author: 2026-05-26 / Codex
- Decision: Return investment_plan as a serialized dictionary derived from InvestmentPlan rather than a raw markdown string.
  Rationale: Downstream crews need stable fields, and task-level structured output made that contract reliable enough to test directly.
  Date/Author: 2026-05-26 / Codex
- Decision: Resolve the research round count from `settings.py` by default.
  Rationale: Debate length needs to be tunable through the same runtime configuration surface as analyst-stage limits instead of being hard-coded at call sites.
  Date/Author: 2026-06-05 / Codex
- Decision: Default `research_stage.max_rounds` to 1.
  Rationale: One bull turn and one bear turn should be the baseline; deeper debate can be enabled through runtime configuration when needed.
  Date/Author: 2026-06-05 / Codex
- Decision: Persist `debate_history.md` and `investment_plan.md` alongside the analyst reports.
  Rationale: The research stage is now part of the main flow, and users need the same inspectable artifacts for research outputs as they already have for analyst outputs.
  Date/Author: 2026-06-05 / Codex

## Outcomes & Retrospective

The research-stage helper is implemented and wired into the main TradingAgents flow. run_research_stage validates the four analyst reports, runs bull and bear turns for exactly the configured maximum rounds, accumulates an ordered plain-text transcript, and returns a serialized investment_plan dictionary derived from InvestmentPlan. The full test suite validates crew wiring, transcript ordering, settings-backed max-round debate control, flow integration, output persistence, and the manager output contract.

## Context and Orientation

The current repository already implements the analyst stage in `src/trading_agents/crews/analyst_crew/analyst_crew.py` and wires it into a traced analyst-only flow in `src/trading_agents/main.py`. That analyst stage returns four string reports under these keys:

    fundamentals_report
    sentiment_report
    news_report
    market_report

This plan adds the next stage only. Create a new directory:

    src/trading_agents/crews/research_crew/

That directory should contain `research_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, following the same repository pattern used by the analyst crew.

A debate history in this repository is a plain text transcript assembled in execution order. A stage helper is a small Python function that prepares inputs, runs a crew one or more times, and returns stable keys to the caller. A structured output is a Pydantic model that downstream code can consume without scraping prose.

## Plan of Work

First, create or extend `src/trading_agents/schemas.py` with one small model:

    class InvestmentPlan(BaseModel):
        rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
        thesis: str
        supporting_evidence: list[str]
        key_risks: list[str]
        recommended_action: str

Second, implement `src/trading_agents/crews/research_crew/research_crew.py`. Import and call `load_dotenv()` near the top of the module. Define `ResearchCrew` with three agents named `bull_researcher`, `bear_researcher`, and `research_manager`, and three tasks named `bull_research`, `bear_research`, and `research_management`. Keep the crew sequential and traced.

Third, implement `run_research_stage(inputs, max_rounds=None)`. That helper should validate that all four analyst reports are present, resolve `max_rounds` from `settings.py` when the caller does not provide it, initialize an empty `debate_history`, and then loop through bull and bear turns in order until the round counter reaches `max_rounds`. Each turn should receive the four analyst reports plus the current debate history and the other side's latest response. After each turn, append the raw response to `debate_history`. After each completed round, run the research manager task to produce the latest `InvestmentPlan`. The helper should return at least:

    {
        "debate_history": "...",
        "investment_plan": "...",
    }

If structured parsing works reliably with CrewAI for this model, return the parsed object or its serialized form consistently. If structured parsing proves unstable, keep the task prompt strongly structured and document the fallback serialization in this plan.

Fourth, write the prompts in `src/trading_agents/crews/research_crew/config/agents.yaml` and `src/trading_agents/crews/research_crew/config/tasks.yaml`. The bull prompt should argue for upside and rebut the bear case. The bear prompt should argue downside and rebut the bull case. The manager prompt should synthesize the transcript into the `InvestmentPlan` structure without inventing missing evidence.

Fifth, add focused tests. Create:

    tests/test_research_crew_config.py
    tests/test_research_stage_contracts.py

The config test should verify that YAML keys match crew methods and that task-to-agent bindings are correct. The contract test should mock crew outputs to prove that the helper accumulates debate history in order, runs exactly `max_rounds` rounds, and returns a stable `investment_plan` key.

Sixth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_research_stage.py`, that feeds local sample analyst reports into `run_research_stage` and prints the resulting keys. Keep it independent from the later trader, risk, and portfolio stages.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the analyst helper exists:

       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage; print(run_analyst_stage.__name__)"

2. Create the research crew files and shared schema file if they do not exist yet:

       src/trading_agents/schemas.py
       src/trading_agents/crews/research_crew/research_crew.py
       src/trading_agents/crews/research_crew/config/agents.yaml
       src/trading_agents/crews/research_crew/config/tasks.yaml

3. Add the focused tests:

       tests/test_research_crew_config.py
       tests/test_research_stage_contracts.py

4. Run the research-stage test suite:

       uv run pytest tests/test_research_crew_config.py tests/test_research_stage_contracts.py

   Expected success:

       passed

5. If a smoke helper is added, run it with local sample inputs:

       uv run python -m trading_agents.dev_smoke_research_stage

   Expected behavior: the script prints that it produced `debate_history` and `investment_plan`.

## Validation and Acceptance

Acceptance requires all of the following behaviors:

- The new `research_crew` package imports successfully.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_research_stage` rejects missing analyst reports with a clear error before any live LLM work starts.
- The research stage builds an ordered `debate_history` transcript from bull and bear outputs.
- The research stage returns an `investment_plan` derived from the four analyst reports plus the debate transcript.
- Mocked tests pass without network or live LLM calls.

If the manager output uses structured parsing, add one contract test that proves the parsed object contains the expected rating and thesis fields. If the manager output uses free text, document the exact returned string contract in the tests and in this file.

## Idempotence and Recovery

All work in this plan is additive. The stage helper can be run repeatedly with the same mock inputs. If a round-loop bug appears, fix the helper and rerun the focused tests; no external state should need cleanup. Any optional debug output should live under `output/debug/` and be safe to overwrite.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Research Crew plan so the decision-stage work can proceed one crew at a time.

Revision Note: 2026-05-26 updated progress, discoveries, decisions, and outcomes after implementing and validating the research crew milestone.
