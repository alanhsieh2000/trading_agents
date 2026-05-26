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
- [ ] Confirm `plans/04_trader_crew.md` has produced a stable `trader_plan` output.
- [ ] Extend shared schemas with the risk-stage contract.
- [ ] Implement `risk_management_crew` with iterative debate-history handling.
- [ ] Add mocked config and contract tests for the risk stage.
- [ ] Run focused tests and one small smoke helper, then record the results here.
- [ ] Preserve the runtime conventions established in earlier plans: `load_dotenv()` before live runs, `llm: gpt-4o-mini` in YAML, and `tracing=True` on the crew.

## Surprises & Discoveries

- Observation: The README text appears to contain a role-name typo for the conservative debator.
  Evidence: The earlier combined plan recorded that the Risk Management Crew section repeats `Aggressive Risk Debator` where the surrounding description clearly implies a separate conservative role.
- Observation: The risk stage needs deterministic stopping behavior across three participants, not two.
  Evidence: Bull-versus-bear stop logic from research is not sufficient here because the risk transcript must preserve aggressive, conservative, and neutral turns in exact order.

## Decision Log

- Decision: Correct the README typo locally by implementing a `conservative_risk_debator`.
  Rationale: The role name, task title, and described behavior all point to a distinct conservative agent; reusing the aggressive agent name would create a misleading interface.
  Date/Author: 2026-05-26 / Codex
- Decision: Add `RiskOpinion` to `src/trading_agents/schemas.py` in this plan.
  Rationale: The risk debate introduces a new structured unit that later plans should consume directly instead of inventing ad hoc strings.
  Date/Author: 2026-05-26 / Codex
- Decision: Use the same explicit `HAS_MORE: yes` or `HAS_MORE: no` trailer pattern as the research debate.
  Rationale: Deterministic parsing and testability matter more than trying to infer conversational completeness from raw prose.
  Date/Author: 2026-05-26 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a single runnable risk-stage helper that accepts analyst reports plus a trader plan and returns a stable `risk_debate_history`. Update this section after implementation and validation.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md`, the research stage from `plans/03_research_crew.md`, and the trader stage from `plans/04_trader_crew.md`. Those earlier stages provide the four analyst reports and the `trader_plan` that the risk stage consumes.

Create a new directory:

    src/trading_agents/crews/risk_management_crew/

That directory should contain `risk_management_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by other crews.

In this repository, the risk debate history is a plain text transcript assembled in exact execution order. The neutral debator does not erase the aggressive and conservative views; it balances them and highlights missing caution or missing upside.

## Plan of Work

First, extend `src/trading_agents/schemas.py` with:

    class RiskOpinion(BaseModel):
        speaker: Literal["Aggressive", "Conservative", "Neutral"]
        response: str
        has_more: bool = True

Second, implement `src/trading_agents/crews/risk_management_crew/risk_management_crew.py`. Import and call `load_dotenv()` near the top of the module. Define `RiskManagementCrew` with three agents named `aggressive_risk_debator`, `conservative_risk_debator`, and `neutral_risk_debator`, and three tasks named `aggressive_risk_opinion`, `conservative_risk_opinion`, and `neutral_risk_opinion`. Keep the crew sequential and traced.

Third, implement `run_risk_stage(inputs, max_rounds=2)`. That helper should validate the presence of the four analyst reports and the `trader_plan`, initialize an empty `risk_debate_history`, and run aggressive, conservative, and neutral turns in that order. After each response, append it to the transcript. Stop early only when all active participants signal `HAS_MORE: no` for the current round. Return at least:

    {
        "risk_debate_history": "...",
    }

If structured parsing works for individual opinions, keep it. If not, parse only the `HAS_MORE` trailer and preserve the transcript as plain text.

Fourth, write the prompts in `src/trading_agents/crews/risk_management_crew/config/agents.yaml` and `src/trading_agents/crews/risk_management_crew/config/tasks.yaml`. The aggressive role should emphasize upside and challenge excessive caution. The conservative role should emphasize capital preservation and downside protection. The neutral role should weigh both and point out overconfidence or overreaction. Every opinion task should end with the explicit `HAS_MORE` trailer.

Fifth, add focused tests. Create:

    tests/test_risk_management_crew_config.py
    tests/test_risk_stage_contracts.py

The config test should verify method names, YAML keys, and task-to-agent bindings. The contract test should mock the risk-stage outputs to prove that `run_risk_stage` validates required inputs, preserves transcript order, and stops according to the explicit trailer rule.

Sixth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_risk_stage.py`, that feeds local sample reports and a sample trader plan into `run_risk_stage` and prints the resulting keys.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the trader helper exists after plan 04:

       uv run python -c "from trading_agents.crews.trader_crew.trader_crew import run_trader_stage; print(run_trader_stage.__name__)"

2. Create the risk crew files if they do not exist yet:

       src/trading_agents/crews/risk_management_crew/risk_management_crew.py
       src/trading_agents/crews/risk_management_crew/config/agents.yaml
       src/trading_agents/crews/risk_management_crew/config/tasks.yaml

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
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_risk_stage` rejects missing analyst reports or missing `trader_plan` with a clear error before any live LLM work starts.
- The risk stage returns an ordered `risk_debate_history` transcript containing aggressive, conservative, and neutral turns in execution order.
- The stage stop condition is deterministic and covered by tests.
- Mocked tests pass without network or live LLM calls.

If individual opinions are structured, add one contract test that proves `speaker` and `has_more` survive parsing correctly. If opinions are kept as free text, document that contract here and in the test file.

## Idempotence and Recovery

All work in this plan is additive. The risk helper can be rerun safely with the same mock inputs. If one role's prompt causes unstable `HAS_MORE` output, tighten that single prompt and parser without changing the downstream transcript contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Risk Management Crew plan so the decision-stage work can proceed one crew at a time.
