# Implement the Portfolio Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can take the research plan, trader plan, and risk debate and turn them into the final portfolio-stage approval or rejection required by the README. A user should be able to inspect the portfolio manager's initial decision, self-critique, and final exact `approve` or `reject` output before the end-to-end flow wiring begins.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Portfolio Crew before starting the final flow-and-evaluation plan.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Portfolio Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream portfolio-stage source summaries and the earlier combined decision-stage plan notes.
- [x] (2026-05-26 00:00Z) Split the former combined decision-stage plan so portfolio work can proceed independently after Risk Management Crew completion.
- [ ] Confirm `plans/05_risk_management_crew.md` has produced a stable `risk_debate_history` output.
- [ ] Extend shared schemas with the portfolio-stage contract and any normalization helper.
- [ ] Implement `portfolio_crew` with three sequential portfolio tasks.
- [ ] Add mocked config and contract tests for the portfolio stage.
- [ ] Run focused tests and one small smoke helper, then record the results here.
- [ ] Preserve the runtime conventions established in earlier plans: `load_dotenv()` before live runs, `llm: gpt-4o-mini` in YAML, and `tracing=True` on the crew.

## Surprises & Discoveries

- Observation: The project's final portfolio output contract is narrower than the richer internal reasoning expected from the manager.
  Evidence: The earlier combined plan recorded that the README requires the final portfolio decision to be exactly one lower-case word, `approve` or `reject`, even though the upstream source uses richer rating scales internally.
- Observation: The end-to-end flow will later map portfolio rejection to a final user-facing `Hold`, so this stage must not do that mapping itself.
  Evidence: The current flow plan says the portfolio stage returns the exact trade decision and the flow performs the final result mapping afterwards.

## Decision Log

- Decision: Add `PortfolioDecision` to `src/trading_agents/schemas.py` in this plan.
  Rationale: The binary approval contract belongs to the portfolio stage and should be defined where it is introduced.
  Date/Author: 2026-05-26 / Codex
- Decision: Keep any rationale separate from the final single-word contract.
  Rationale: The flow depends on a strict `approve` or `reject` value, but humans still need supporting reasoning for inspection and debugging.
  Date/Author: 2026-05-26 / Codex
- Decision: Add a narrow normalization or fallback parser if the model emits punctuation or extra prose.
  Rationale: The final contract is strict enough that small formatting drift should be corrected or rejected deterministically rather than silently passed through.
  Date/Author: 2026-05-26 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a single runnable portfolio-stage helper that accepts the research plan, trader plan, and risk debate and returns a stable final `approve` or `reject` value plus any separately stored rationale. Update this section after implementation and validation.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md`, the research stage from `plans/03_research_crew.md`, the trader stage from `plans/04_trader_crew.md`, and the risk stage from `plans/05_risk_management_crew.md`.

Create a new directory:

    src/trading_agents/crews/portfolio_crew/

That directory should contain `portfolio_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by other crews.

In this repository, the final trade decision is the portfolio crew's exact `approve` or `reject` result. The later flow-level final output is different and will be handled in the next plan.

## Plan of Work

First, extend `src/trading_agents/schemas.py` with:

    class PortfolioDecision(BaseModel):
        decision: Literal["approve", "reject"]
        rationale: str

Second, implement `src/trading_agents/crews/portfolio_crew/portfolio_crew.py`. Import and call `load_dotenv()` near the top of the module. Define `PortfolioCrew` with one agent named `portfolio_manager` and three tasks named `initial_trade_decision`, `portfolio_self_reflection`, and `final_trade_decision`. Keep the crew sequential and traced.

Third, implement `run_portfolio_stage(inputs)`. That helper should validate the presence of `investment_plan`, `trader_plan`, and `risk_debate_history`, normalize the inputs, kick off the portfolio crew once, and return at least:

    {
        "final_trade_decision": "approve" or "reject",
    }

If CrewAI structured output works reliably, parse the portfolio decision into `PortfolioDecision`. If not, preserve a human-readable rationale separately and use a narrow normalization helper that either converts trivial variants such as `Approve.` into `approve` or raises a clear error when the output is ambiguous.

Fourth, write the prompts in `src/trading_agents/crews/portfolio_crew/config/agents.yaml` and `src/trading_agents/crews/portfolio_crew/config/tasks.yaml`. The initial task should synthesize the research plan, trader plan, and risk debate. The self-reflection task should challenge imbalance between opportunity and risk. The final task should emit the definitive approval contract in the chosen format.

Fifth, add focused tests. Create:

    tests/test_portfolio_crew_config.py
    tests/test_portfolio_stage_contracts.py

The config test should verify method names, YAML keys, and task-to-agent bindings. The contract test should mock the final crew output to prove that `run_portfolio_stage` validates required inputs, returns only `approve` or `reject`, and handles malformed model output according to the documented parser behavior.

Sixth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_portfolio_stage.py`, that feeds local sample inputs into `run_portfolio_stage` and prints the resulting keys.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the risk helper exists after plan 05:

       uv run python -c "from trading_agents.crews.risk_management_crew.risk_management_crew import run_risk_stage; print(run_risk_stage.__name__)"

2. Create the portfolio crew files if they do not exist yet:

       src/trading_agents/crews/portfolio_crew/portfolio_crew.py
       src/trading_agents/crews/portfolio_crew/config/agents.yaml
       src/trading_agents/crews/portfolio_crew/config/tasks.yaml

3. Add the focused tests:

       tests/test_portfolio_crew_config.py
       tests/test_portfolio_stage_contracts.py

4. Run the portfolio-stage test suite:

       uv run pytest tests/test_portfolio_crew_config.py tests/test_portfolio_stage_contracts.py

   Expected success:

       passed

5. If a smoke helper is added, run it with local sample inputs:

       uv run python -m trading_agents.dev_smoke_portfolio_stage

   Expected behavior: the script prints that it produced `final_trade_decision`.

## Validation and Acceptance

Acceptance requires all of the following behaviors:

- The new `portfolio_crew` package imports successfully.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_portfolio_stage` rejects missing upstream artifacts with a clear error before any live LLM work starts.
- The portfolio stage returns exactly `approve` or `reject` in lower case for the final decision value.
- Parser or normalizer behavior for malformed outputs is covered by tests and documented here.
- Mocked tests pass without network or live LLM calls.

The parser test set must include at least malformed variants such as `Approve.` and `APPROVE because...` so the implementation documents whether they are normalized or rejected.

## Idempotence and Recovery

All work in this plan is additive. The portfolio helper can be rerun safely with the same mock inputs. If the model output drifts, adjust the narrow normalization helper and rerun focused tests without changing the downstream contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Portfolio Crew plan so the decision-stage work can proceed one crew at a time.
