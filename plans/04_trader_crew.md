# Implement the Trader Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can turn a completed research-stage investment plan into a trader-stage transaction proposal with an explicit self-critique step and a final trader output. A user should be able to inspect how the trader moved from the research decision into an actionable `BUY`, `HOLD`, or `SELL` plan before any risk debate begins.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Trader Crew before starting the Risk Management Crew.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Trader Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream trader-stage source summaries and the earlier combined decision-stage plan notes.
- [x] (2026-05-26 00:00Z) Split the former combined decision-stage plan so Trader work can proceed independently after Research Crew completion.
- [ ] Confirm `plans/03_research_crew.md` has produced a stable `investment_plan` output.
- [ ] Extend shared schemas with the trader-stage contract.
- [ ] Implement `trader_crew` with three sequential trader tasks.
- [ ] Add mocked config and contract tests for the trader stage.
- [ ] Run focused tests and one small smoke helper, then record the results here.
- [ ] Preserve the runtime conventions established in plan 02 and plan 03: `load_dotenv()` before live runs, `llm: gpt-4o-mini` in YAML, and `tracing=True` on the crew.

## Surprises & Discoveries

- Observation: The upstream TradingAgents source can collapse trader reasoning into a single structured call, but the local README requires three tasks.
  Evidence: The earlier combined plan documented that the local product spec expects `initial_trader_plan`, `trader_self_reflection`, and `final_trader_plan`, which gives a clearer audit trail than one opaque call.
- Observation: The trader stage depends on both the research result and the original analyst evidence.
  Evidence: The combined plan notes say the self-reflection task should check whether the proposal is grounded in the analyst reports and the research plan, so this stage cannot be defined as a pure transformation of only the rating.

## Decision Log

- Decision: Keep the Trader Crew as one agent with three tasks instead of multiple agents.
  Rationale: The repository README already defines the trader stage that way, and a single agent with self-reflection is easier to test than debate-style multi-agent behavior.
  Date/Author: 2026-05-26 / Codex
- Decision: Add `TraderPlan` to `src/trading_agents/schemas.py` in this plan.
  Rationale: This is the first stage that needs the trader-specific output contract, and later plans should consume it rather than redefining it.
  Date/Author: 2026-05-26 / Codex
- Decision: Preserve access to the analyst reports during self-reflection and finalization.
  Rationale: The trader output should stay evidence-backed instead of drifting into a summary of the research manager's prose alone.
  Date/Author: 2026-05-26 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a single runnable trader-stage helper that accepts analyst reports plus a research-stage investment plan and returns a stable `trader_plan`. Update this section after implementation and validation.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md` and the research stage from `plans/03_research_crew.md`. Those earlier stages provide the four analyst reports plus the `investment_plan` that the trader stage consumes.

Create a new directory:

    src/trading_agents/crews/trader_crew/

That directory should contain `trader_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by the analyst crew and the planned research crew.

In this repository, a self-reflection task means the same agent critiques its own earlier output and then improves it in a later task. The trader plan is the stage output that later feeds the risk debate.

## Plan of Work

First, extend `src/trading_agents/schemas.py` with:

    class TraderPlan(BaseModel):
        action: Literal["BUY", "HOLD", "SELL"]
        rationale: str
        evidence_used: list[str]
        risk_controls: list[str]

Second, implement `src/trading_agents/crews/trader_crew/trader_crew.py`. Import and call `load_dotenv()` near the top of the module. Define `TraderCrew` with one agent named `trader_agent` and three tasks named `initial_trader_plan`, `trader_self_reflection`, and `final_trader_plan`. Keep the crew sequential and traced.

Third, implement `run_trader_stage(inputs)`. That helper should validate the presence of the four analyst reports and the research-stage `investment_plan`, normalize the inputs, kick off the trader crew once, and return at least:

    {
        "trader_plan": "...",
    }

If CrewAI structured output works reliably here, parse the final trader task into `TraderPlan`. If not, make the final prompt strongly structured and document the exact free-text contract plus any fallback parsing behavior.

Fourth, write the prompts in `src/trading_agents/crews/trader_crew/config/agents.yaml` and `src/trading_agents/crews/trader_crew/config/tasks.yaml`. The initial task should convert the investment plan into a transaction recommendation. The self-reflection task should challenge unsupported claims, weak evidence, and missing risk controls. The final task should emit the definitive `BUY`, `HOLD`, or `SELL` plan in the agreed contract.

Fifth, add focused tests. Create:

    tests/test_trader_crew_config.py
    tests/test_trader_stage_contracts.py

The config test should verify method names, YAML keys, and task-to-agent bindings. The contract test should mock the final crew output to prove that `run_trader_stage` validates required inputs and returns a stable `trader_plan`.

Sixth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_trader_stage.py`, that feeds local sample analyst reports and an example investment plan into `run_trader_stage` and prints the resulting keys. Keep it independent from later risk and portfolio logic.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the research helper exists after plan 03:

       uv run python -c "from trading_agents.crews.research_crew.research_crew import run_research_stage; print(run_research_stage.__name__)"

2. Create the trader crew files if they do not exist yet:

       src/trading_agents/crews/trader_crew/trader_crew.py
       src/trading_agents/crews/trader_crew/config/agents.yaml
       src/trading_agents/crews/trader_crew/config/tasks.yaml

3. Add the focused tests:

       tests/test_trader_crew_config.py
       tests/test_trader_stage_contracts.py

4. Run the trader-stage test suite:

       uv run pytest tests/test_trader_crew_config.py tests/test_trader_stage_contracts.py

   Expected success:

       passed

5. If a smoke helper is added, run it with local sample inputs:

       uv run python -m trading_agents.dev_smoke_trader_stage

   Expected behavior: the script prints that it produced `trader_plan`.

## Validation and Acceptance

Acceptance requires all of the following behaviors:

- The new `trader_crew` package imports successfully.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_trader_stage` rejects missing analyst reports or missing `investment_plan` with a clear error before any live LLM work starts.
- The trader stage returns a stable `trader_plan` contract that later stages can consume.
- The final trader result contains one of `BUY`, `HOLD`, or `SELL`.
- Mocked tests pass without network or live LLM calls.

If the trader result is structured, add one contract test that proves the parsed object preserves action, rationale, and risk controls. If the trader result is free text, document the serialization contract here and in the test file.

## Idempotence and Recovery

All work in this plan is additive. The trader helper can be rerun safely with the same mock inputs. If structured output proves unreliable, keep the prompts and tests stable while adding a narrow fallback parser rather than changing the downstream contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Trader Crew plan so the decision-stage work can proceed one crew at a time.
