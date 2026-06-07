# Implement the Risk Management Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can take the analyst reports plus the trader plan and run the explicit risk debate required by the README. A user should be able to inspect aggressive, conservative, and neutral risk positions in sequence before any final portfolio approval or rejection is made.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Risk Management Crew before starting the Portfolio Crew.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Risk Management Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream risk-stage source summaries and the earlier combined decision-stage plan notes.
- [x] (2026-05-26 00:00Z) Split the former combined decision-stage plan so risk work can proceed independently after Trader Crew completion.
- [x] (2026-06-05 00:00Z) Aligned this plan with the plan 03 implementation pattern: settings-backed LLM resolution, settings-backed stage tuning, and flow wiring in `main.py`.
- [x] (2026-06-07 06:16Z) Confirmed `plans/04_trader_crew.md` has produced a stable `trader_plan` output by importing `run_trader_stage`.
- [x] (2026-06-07 06:16Z) Confirmed the risk stage uses the plain transcript contract and does not need a `RiskOpinion` schema.
- [x] (2026-06-07 06:16Z) Implemented `risk_management_crew` with iterative aggressive, conservative, and neutral debate-history handling.
- [x] (2026-06-07 06:16Z) Added mocked config and contract tests for the risk stage.
- [x] (2026-06-07 06:16Z) Ran focused risk and flow tests, then the full test suite.
- [x] (2026-06-07 06:16Z) Preserved the runtime conventions established in earlier plans: `load_dotenv()` before live runs, `llm_level` in YAML resolved by `resolve_agent_config()`, runtime tunables in `config/settings.py`, `tracing=True` on the crew, and flow integration through `TradingAgentsFlow`.
- [x] (2026-06-07 07:49Z) Removed the obsolete `HAS_MORE` stop contract; `max_rounds`, defaulting to 1, is now the only risk-stage iteration stop.
- [x] (2026-06-07 07:49Z) Renamed the risk YAML and crew methods to align with `PROMPTS.md`: `aggressive_analyst`, `conservative_analyst`, `neutral_analyst`, and `*_risk_analysis` task names.

## Surprises & Discoveries

- Observation: The README text appears to contain a role-name typo for the conservative debator.
  Evidence: The earlier combined plan recorded that the Risk Management Crew section repeats `Aggressive Risk Debator` where the surrounding description clearly implies a separate conservative role.
- Observation: The risk stage needs deterministic stopping behavior across three participants, not two.
  Evidence: Bull-versus-bear stop logic from research is not sufficient here because the risk transcript must preserve aggressive, conservative, and neutral turns in exact order.
- Observation: Plan 03 moved stage-loop tuning into runtime settings.
  Evidence: Research max rounds are resolved from `get_settings().research_stage.max_rounds` when the caller does not provide an override; risk debate max rounds should follow the same pattern instead of hard-coding a default at call sites.
- Observation: Individual risk opinions are kept as free text instead of CrewAI `output_pydantic` task outputs.
  Evidence: The implemented prompts require conversational debate text, and `tests/test_risk_stage_contracts.py` verifies ordered transcript assembly without structured opinion parsing.
- Observation: The `PROMPTS.md` neutral YAML example repeats the key `conservative_risk_analysis`.
  Evidence: YAML cannot contain two distinct task entries with the same key for a three-task CrewAI crew, so the implementation uses `neutral_risk_analysis` for the neutral task while preserving the prompt wording.

## Decision Log

- Decision: Correct the README typo locally by implementing a `conservative_analyst`.
  Rationale: The role name, task title, and described behavior all point to a distinct conservative agent; reusing the aggressive agent name would create a misleading interface.
  Date/Author: 2026-05-26 / Codex
- Decision: Do not add `RiskOpinion` to `src/trading_agents/schemas.py`.
  Rationale: The risk-stage output consumed by later stages is the full ordered debate transcript, not individual structured risk opinions.
  Date/Author: 2026-06-07 / Codex
- Decision: Do not use `HAS_MORE` or any opinion-level stop signal in the risk stage.
  Rationale: `PROMPTS.md` specifies that the risk debate iterates until the round counter reaches the maximum. The configured `max_rounds` is therefore the only stop condition.
  Date/Author: 2026-06-07 / Codex
- Decision: Configure all three risk analysts with `llm_level: quick_llm`.
  Rationale: Only the portfolio manager uses `deep_llm`; aggressive, conservative, and neutral risk analysts are non-portfolio agents and should use the settings-backed quick model.
  Date/Author: 2026-06-05 / Codex
- Decision: Add `RiskStageSettings.max_rounds` to `src/trading_agents/config/settings.py`.
  Rationale: Debate length is a runtime tuning knob and should use the same environment-overridable settings surface as research-stage max rounds.
  Date/Author: 2026-06-05 / Codex
- Decision: Wire the risk stage into `TradingAgentsFlow` as part of this plan.
  Rationale: Plan 03 established that newly completed stages should be part of the main flow and saved as inspectable run artifacts.
  Date/Author: 2026-06-05 / Codex
- Decision: Preserve each raw debate turn in `risk_debate_history`.
  Rationale: Keeping the full generated text makes the transcript auditable; loop control comes only from `max_rounds`.
  Date/Author: 2026-06-07 / Codex

## Outcomes & Retrospective

Implemented the Risk Management Crew and wired it into `TradingAgentsFlow`. The project now has a runnable `run_risk_stage(inputs, max_rounds=None)` helper that validates analyst reports plus the trader plan, runs aggressive, conservative, and neutral turns in order for exactly the configured number of rounds, and returns a stable `risk_debate_history` transcript. The default risk debate length is one round through `RiskStageSettings(max_rounds=1)`. The main flow persists the transcript as `risk_debate_history.md` beside the analyst, research, and trader artifacts.

Validation completed on 2026-06-07:

    uv run pytest tests/test_risk_management_crew_config.py tests/test_risk_stage_contracts.py tests/test_runtime_settings.py tests/test_trading_flow.py
    25 passed

    uv run pytest tests/test_risk_management_crew_config.py tests/test_risk_stage_contracts.py tests/test_trading_flow.py
    16 passed

    uv run pytest
    77 passed

No smoke helper was added because the mocked contract tests exercise the risk-stage helper and the flow persistence path without requiring live LLM credentials.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md`, the research stage from `plans/03_research_crew.md`, and the trader stage from `plans/04_trader_crew.md`. Those earlier stages provide the four analyst reports and the `trader_plan` that the risk stage consumes. Extend the existing `TradingAgentsFlow` rather than adding a separate orchestration path.

Create a new directory:

    src/trading_agents/crews/risk_management_crew/

That directory should contain `risk_management_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by other crews.

In this repository, the risk debate history is a plain text transcript assembled in exact execution order. The neutral analyst does not erase the aggressive and conservative views; it balances them and highlights missing caution or missing upside.

## Plan of Work

First, keep the risk-stage output contract as plain text. No `RiskOpinion` schema is required because later stages consume the complete `risk_debate_history` transcript.

Second, extend `src/trading_agents/config/settings.py` with `RiskStageSettings(max_rounds=1)` and add it to `AppSettings` and `trading_agents.config.__all__`. Any future risk-stage tuning constants should be added to settings rather than hard-coded in the helper or flow.

Third, implement `src/trading_agents/crews/risk_management_crew/risk_management_crew.py`. Import and call `load_dotenv()` near the top of the module. Import `get_settings` and `resolve_agent_config` from `trading_agents.config`; pass `config=resolve_agent_config(self.agents_config[...])` when constructing each agent. Define `RiskManagementCrew` with three agents named `aggressive_analyst`, `conservative_analyst`, and `neutral_analyst`, and three tasks named `aggressive_risk_analysis`, `conservative_risk_analysis`, and `neutral_risk_analysis`. Keep the crew sequential and traced.

Fourth, implement `run_risk_stage(inputs, max_rounds=None)`. When `max_rounds` is `None`, resolve it from `get_settings().risk_stage.max_rounds`. The helper should validate the presence of the four analyst reports and the `trader_plan`, initialize an empty `risk_debate_history`, and run aggressive, conservative, and neutral turns in that order. After each response, append it to the transcript. Stop only when the configured round count is reached. Return at least:

    {
        "risk_debate_history": "...",
    }

Do not parse individual risk opinions or look for a `HAS_MORE` trailer. Preserve the transcript as plain text.

Fifth, wire the risk stage into `src/trading_agents/main.py`. Import `run_risk_stage`, add `risk_debate_history` to `TradingAgentsState`, add a `@listen` method after the trader stage that passes the four analyst reports, `ticker`, `trade_date`, and `trader_plan` into `run_risk_stage`, and persist the risk debate history with the other run outputs.

Sixth, write the prompts in `src/trading_agents/crews/risk_management_crew/config/agents.yaml` and `src/trading_agents/crews/risk_management_crew/config/tasks.yaml`. Follow the `PROMPTS.md` Risk Management Team section: aggressive analysis should emphasize upside and challenge excessive caution, conservative analysis should emphasize capital preservation and downside protection, and neutral analysis should weigh both perspectives and point out overconfidence or overreaction. Every risk agent YAML entry must use `llm_level: quick_llm`, `allow_delegation: false`, and `verbose: true`; do not set literal `llm` values. Opinion tasks should output conversational text without special formatting and should not include `HAS_MORE`.

Seventh, add focused tests. Create:

    tests/test_risk_management_crew_config.py
    tests/test_risk_stage_contracts.py

The config test should verify method names, YAML keys, task-to-agent bindings, `llm_level: quick_llm` for all risk agents, absence of literal `llm` in the agent YAML, and absence of `HAS_MORE` in task prompts. The contract test should mock the risk-stage outputs to prove that `run_risk_stage` validates required inputs, preserves transcript order, resolves `max_rounds` from settings by default, and runs exactly the configured number of rounds. Add a flow test that mocks `run_risk_stage` and proves `TradingAgentsFlow` passes through and persists the risk debate history.

Eighth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_risk_stage.py`, that feeds local sample reports and a sample trader plan into `run_risk_stage` and prints the resulting keys.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the trader helper exists after plan 04:

       uv run python -c "from trading_agents.crews.trader_crew.trader_crew import run_trader_stage; print(run_trader_stage.__name__)"

2. Create the risk crew files if they do not exist yet:

       src/trading_agents/crews/risk_management_crew/risk_management_crew.py
       src/trading_agents/crews/risk_management_crew/config/agents.yaml
       src/trading_agents/crews/risk_management_crew/config/tasks.yaml

   Update `src/trading_agents/config/settings.py`, `src/trading_agents/config/__init__.py`, and `src/trading_agents/main.py` in the same pass.

3. Add the focused tests:

       tests/test_risk_management_crew_config.py
       tests/test_risk_stage_contracts.py

4. Run the risk-stage test suite:

       uv run pytest tests/test_risk_management_crew_config.py tests/test_risk_stage_contracts.py

   Expected success:

       passed

5. If a smoke helper is added, run it with local sample inputs:

       uv run python -m trading_agents.dev_smoke_risk_stage

   Expected behavior: the script prints that it produced `risk_debate_history`.

## Validation and Acceptance

Acceptance requires all of the following behaviors:

- The new `risk_management_crew` package imports successfully.
- All risk agents use `llm_level: quick_llm` and the crew class resolves it through `resolve_agent_config()`.
- Risk debate `max_rounds` defaults through `get_settings().risk_stage.max_rounds` and remains overrideable for tests.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_risk_stage` rejects missing analyst reports or missing `trader_plan` with a clear error before any live LLM work starts.
- The risk stage returns an ordered `risk_debate_history` transcript containing aggressive, conservative, and neutral turns in execution order.
- `TradingAgentsFlow` runs the risk stage after trader, stores `risk_debate_history` in state, and saves the risk output beside earlier stage artifacts.
- The stage stop condition is deterministic, based only on `max_rounds`, and covered by tests.
- Mocked tests pass without network or live LLM calls.

## Idempotence and Recovery

All work in this plan is additive. The risk helper can be rerun safely with the same mock inputs. If one role's prompt is unstable, tighten that single prompt without changing the downstream transcript contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Risk Management Crew plan so the decision-stage work can proceed one crew at a time.

Revision Note: 2026-06-07 implemented the Risk Management Crew, recorded the plain-text transcript contract, and added validation evidence from the focused and full test suites.

Revision Note: 2026-06-07 removed the obsolete `HAS_MORE` stop condition, changed the risk default to one round, aligned the YAML names with `PROMPTS.md`, and documented that `max_rounds` is the only iteration stop.
