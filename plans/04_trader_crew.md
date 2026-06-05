# Implement the Trader Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can turn a completed research-stage investment plan into a trader-stage transaction proposal. The Trader Crew has one trading agent and one `trader_decision` task that emits a structured trader plan, represented by `TraderProposal`, before any risk debate begins.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Trader Crew before starting the Risk Management Crew.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Trader Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream trader-stage source summaries and the earlier combined decision-stage plan notes.
- [x] (2026-05-26 00:00Z) Split the former combined decision-stage plan so Trader work can proceed independently after Research Crew completion.
- [x] (2026-06-05 00:00Z) Reconciled this plan with `PROMPTS.md`: the trader stage is now one agent, one task, and a `TraderProposal` structured output.
- [x] (2026-06-05 00:00Z) Aligned this plan with the plan 03 implementation pattern: settings-backed LLM resolution, no direct model strings in YAML, and flow wiring in `main.py`.
- [ ] Confirm `plans/03_research_crew.md` has produced a stable `investment_plan` output.
- [ ] Extend shared schemas with the trader-stage contract.
- [ ] Implement `trader_crew` with one `trader_decision` task.
- [ ] Add mocked config and contract tests for the trader stage.
- [ ] Run focused tests and one small smoke helper, then record the results here.
- [ ] Preserve the runtime conventions established in plan 02 and plan 03: `load_dotenv()` before live runs, `llm_level` in YAML resolved by `resolve_agent_config()`, runtime tunables in `config/settings.py`, `tracing=True` on the crew, and flow integration through `TradingAgentsFlow`.

## Surprises & Discoveries

- Observation: `PROMPTS.md` is the current source of truth for the trader stage and specifies one agent with one task.
  Evidence: `PROMPTS.md` defines `trader_agent`, `trader_decision`, and `output_pydantic=TraderProposal`; it does not define `initial_trader_plan`, `trader_self_reflection`, or `final_trader_plan`.
- Observation: The trader task consumes the research-stage `investment_plan` as its direct input.
  Evidence: The prompt text says the investment plan incorporates current technical market trends, macroeconomic indicators, and social media sentiment, then asks the trader to use that plan as the foundation for the next trading decision.
- Observation: Plan 03 moved model selection behind `config/settings.py`.
  Evidence: Implemented agents use `llm_level` in YAML and crew classes pass `resolve_agent_config(self.agents_config[...])` to `Agent(...)`, so this plan must not reintroduce literal `llm` model settings in agent YAML.

## Decision Log

- Decision: Keep the Trader Crew as one agent with one task.
  Rationale: `PROMPTS.md` now defines the trader stage as a single structured decision task while keeping it as a crew so self-reflection can be added later if needed.
  Date/Author: 2026-06-05 / Codex
- Decision: Add `TraderAction` and `TraderProposal` to `src/trading_agents/schemas.py` in this plan.
  Rationale: `PROMPTS.md` specifies the trader-stage output contract as a Pydantic model with action, reasoning, optional entry price, optional stop loss, and optional position sizing.
  Date/Author: 2026-06-05 / Codex
- Decision: Use `output_pydantic=TraderProposal` on the `trader_decision` task.
  Rationale: The trader output should be machine-readable for the later risk and portfolio stages instead of relying on free-text parsing.
  Date/Author: 2026-06-05 / Codex
- Decision: Configure `trader_agent` with `llm_level: quick_llm`.
  Rationale: The trader is not the portfolio manager; per the project convention, all non-portfolio-manager agents in plans 04-06 use `quick_llm`.
  Date/Author: 2026-06-05 / Codex
- Decision: Wire the trader stage into `TradingAgentsFlow` as part of this plan.
  Rationale: Plan 03 integrated the research stage directly into `src/trading_agents/main.py`; each later implemented crew should continue the same end-to-end flow rather than remaining as an isolated helper.
  Date/Author: 2026-06-05 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a single runnable trader-stage helper that accepts a ticker plus a research-stage investment plan and returns a stable `trader_plan` represented by `TraderProposal`. The stage should also be wired into `TradingAgentsFlow` and persisted with the rest of the run outputs. Update this section after implementation and validation.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md` and the research stage from `plans/03_research_crew.md`. Those earlier stages provide the `investment_plan` that the trader stage consumes. The current `TradingAgentsFlow` should already prepare inputs, run analysts, run research, store state, and persist analyst and research artifacts; extend that same flow instead of creating a parallel entry point.

Create a new directory:

    src/trading_agents/crews/trader_crew/

That directory should contain `trader_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by the analyst crew and the planned research crew.

The trader plan is the stage output that later feeds the risk debate.

## Plan of Work

First, extend `src/trading_agents/schemas.py` with:

    class TraderAction(str, Enum):
        BUY = "Buy"
        HOLD = "Hold"
        SELL = "Sell"

    class TraderProposal(BaseModel):
        action: TraderAction
        reasoning: str
        entry_price: Optional[float] = None
        stop_loss: Optional[float] = None
        position_sizing: Optional[str] = None

Second, implement `src/trading_agents/crews/trader_crew/trader_crew.py`. Import and call `load_dotenv()` near the top of the module. Import `resolve_agent_config` from `trading_agents.config` and pass `config=resolve_agent_config(self.agents_config["trader_agent"])` when constructing the agent. Define `TraderCrew` with one agent named `trader_agent` and one task named `trader_decision`. Keep the crew sequential and traced. If the implementation introduces any trader-stage runtime knobs or reusable constants, place them in `src/trading_agents/config/settings.py` and export them from `trading_agents.config` instead of adding new hard-coded call-site defaults.

Third, implement `run_trader_stage(inputs)`. That helper should validate the presence of `ticker` and the research-stage `investment_plan`, preserve the ticker exactly as provided including exchange suffixes, normalize the other inputs, kick off the trader crew once, and return at least:

    {
        "trader_plan": TraderProposal(...),
    }

Use CrewAI structured output on the `trader_decision` task with `output_pydantic=TraderProposal`. If structured output proves unreliable, keep the Pydantic contract stable and add a narrow fallback parser rather than changing downstream behavior.

Fourth, wire the trader stage into `src/trading_agents/main.py`. Import `run_trader_stage`, add `trader_plan` to `TradingAgentsState`, add a `@listen(run_research)` method that passes `ticker`, `trade_date`, and `investment_plan` into `run_trader_stage`, and persist the trader plan with the other run outputs. The flow should continue to return the full state dump so later stages can consume the trader output.

Fifth, write the prompts in `src/trading_agents/crews/trader_crew/config/agents.yaml` and `src/trading_agents/crews/trader_crew/config/tasks.yaml`. The agent key must be `trader_agent`; the task key must be `trader_decision`. The trader agent YAML must use `llm_level: quick_llm`, `allow_delegation: false`, and `verbose: true`; do not set a literal `llm`. The agent goal should instruct the model to analyze `{ticker}` and use that exact ticker in every tool call, report, and recommendation. The task should convert the investment plan into a concrete transaction proposal with exactly one action, reasoning, and practical levels for entry, stop-loss, and sizing.

Sixth, add focused tests. Create:

    tests/test_trader_crew_config.py
    tests/test_trader_stage_contracts.py

The config test should verify method names, YAML keys, task-to-agent bindings, `llm_level: quick_llm`, absence of literal `llm` in the agent YAML, and the `output_pydantic=TraderProposal` task contract. The contract test should mock the final crew output to prove that `run_trader_stage` validates required inputs and returns a stable `trader_plan`. Add a flow test that mocks `run_trader_stage` and proves `TradingAgentsFlow` passes through and persists the trader plan.

Seventh, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_trader_stage.py`, that feeds a sample ticker and example investment plan into `run_trader_stage` and prints the resulting keys. Keep it independent from later risk and portfolio logic.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the research helper exists after plan 03:

       uv run python -c "from trading_agents.crews.research_crew.research_crew import run_research_stage; print(run_research_stage.__name__)"

2. Create the trader crew files if they do not exist yet:

       src/trading_agents/crews/trader_crew/trader_crew.py
       src/trading_agents/crews/trader_crew/config/agents.yaml
       src/trading_agents/crews/trader_crew/config/tasks.yaml

   Update `src/trading_agents/main.py` in the same pass so the trader stage is part of `TradingAgentsFlow`.

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
- `trader_agent` uses `llm_level: quick_llm` and the crew class resolves it through `resolve_agent_config()`.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml`.
- `run_trader_stage` rejects missing `ticker` or missing `investment_plan` with a clear error before any live LLM work starts.
- The trader stage returns a stable `trader_plan` contract that later stages can consume.
- `TradingAgentsFlow` runs the trader stage after research, stores `trader_plan` in state, and saves the trader output beside earlier stage artifacts.
- The final trader result contains one of `Buy`, `Hold`, or `Sell`.
- Mocked tests pass without network or live LLM calls.

Add one contract test that proves the parsed object preserves action, reasoning, entry price, stop loss, and position sizing.

## Idempotence and Recovery

All work in this plan is additive. The trader helper can be rerun safely with the same mock inputs. If structured output proves unreliable, keep the prompts and tests stable while adding a narrow fallback parser rather than changing the downstream contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Trader Crew plan so the decision-stage work can proceed one crew at a time.
