# Implement the Portfolio Crew

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can take the research plan, trader plan, and risk debate and turn them into the final portfolio decision required by the README: a structured `PortfolioDecision` that carries a position rating (exactly one of `Buy`, `Overweight`, `Hold`, `Underweight`, or `Sell`) together with an executive summary and an investment thesis.

The Portfolio Crew also learns from its own history. The portfolio manager is a one-person team that plays two roles. In its first role it self-reflects on its own past decisions for the same instrument now that their outcomes are known; in its second role it makes the final decision. Concretely, before deciding on an instrument it has traded before, the stage updates each past decision with its realized return, writes a short plain-prose "lesson" on each, and feeds those lessons into the final decision so the manager does not repeat earlier mistakes.

A user should be able to run the portfolio stage, inspect the lessons that were retrieved and the reflections that were written, and see the manager's final `PortfolioDecision` before the end-to-end flow wiring is finalized.

This plan is intentionally limited to one crew. The goal is to finish coding, prompting, integration, debugging, optimization, and testing for the Portfolio Crew before starting the final flow-and-evaluation plan.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Portfolio Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream portfolio-stage source summaries and the earlier combined decision-stage plan notes.
- [x] (2026-05-26 00:00Z) Split the former combined decision-stage plan so portfolio work can proceed independently after Risk Management Crew completion.
- [x] (2026-06-05 00:00Z) Aligned this plan with the plan 03 implementation pattern: settings-backed LLM resolution, no literal model strings in YAML, and flow wiring in `main.py`.
- [x] (2026-06-09 00:00Z) Realigned this plan with the finalized `PROMPTS.md` "5. Portfolio Manager" specification: two agents (`portfolio_manager` and `self_reflection_manager`) running two tasks (`self_reflection` then `final_decision`), the lesson-record / self-reflection store, the rich `PortfolioDecision` rating contract, and the rule that the deep model is used only for the final decision.
- [ ] Confirm `plans/05_risk_management_crew.md` has produced a stable `risk_debate_history` output.
- [ ] Extend shared schemas with the rich `PortfolioDecision` contract and the lesson-record Pydantic types (`LessonRecord` and the retrieved-lessons list behind `{lessons_line}`).
- [ ] Implement the lesson store: persist a lesson record per decision, resolve the benchmark from the ticker suffix, compute realized returns (raw return, alpha return) and holding days from price data, and build `{lessons_line}`.
- [ ] Implement `portfolio_crew` with two agents (`portfolio_manager`, `self_reflection_manager`) and two sequential tasks (`self_reflection`, `final_decision`).
- [ ] Add mocked config and contract tests for the portfolio stage.
- [ ] Run focused tests and one small smoke helper, then record the results here.
- [ ] Preserve the runtime conventions established in earlier plans: `load_dotenv()` before live runs, `llm_level` in YAML resolved by `resolve_agent_config()`, runtime tunables in `config/settings.py`, `tracing=True` on the crew, and flow integration through `TradingAgentsFlow`.

## Surprises & Discoveries

- Observation: The portfolio manager is a one-person team that the design splits into two CrewAI agents so the crew can both reflect on the past and decide for the present.
  Evidence: `PROMPTS.md` "5. Portfolio Manager" now defines `portfolio_manager` (final decision) and `self_reflection_manager` (self-reflection) in `agents.yaml`, plus tasks `final_decision` and `self_reflection` in `tasks.yaml`.
- Observation: Only the final decision uses the deep model; the self-reflection role uses the quick model.
  Evidence: `PROMPTS.md` closes the section with "The portfolio manager will use a deep LLM only for making the final decision." The settings layer exposes `quick_llm` and `deep_llm`, so `portfolio_manager` resolves to `deep_llm` and `self_reflection_manager` resolves to `quick_llm`; every trader and risk agent stays on `quick_llm`.
- Observation: The final portfolio output contract is the rich `PortfolioDecision` rating, not a single `approve`/`reject` word.
  Evidence: Both `README.md` ("### 5. Portfolio Crew") and `PROMPTS.md` define `PortfolioDecision` with `rating` (`Buy`/`Overweight`/`Hold`/`Underweight`/`Sell`), `executive_summary`, `investment_thesis`, optional `price_target`, and optional `time_horizon`. This supersedes the earlier `approve`/`reject` assumption recorded below on 2026-05-26.
- Observation: `PROMPTS.md` is loosely worded about "alpha return": its second bullet literally describes the benchmark's close-to-close return, while the self-reflection prompt phrases it as "Alpha vs {benchmark_name}".
  Evidence: The self-reflection user prompt is `f"Alpha vs {benchmark_name}: {alpha_return:+.1%}"`, which is the standard meaning of alpha (instrument return relative to benchmark). This plan therefore defines `alpha_return = raw_return - benchmark_return`, where `benchmark_return` is computed by the second bullet's formula. This interpretation is recorded in the Decision Log.
- Observation: The end-to-end flow output is the `PortfolioDecision` itself; there is no portfolio-stage `reject` -> `Hold` remapping.
  Evidence: `README.md` "## Flow" states "The output of the flow is the Portfolio Crew's final trade decision: a `PortfolioDecision` carrying the final position rating and its supporting thesis."

## Decision Log

- Decision: Add `PortfolioDecision` to `src/trading_agents/schemas.py` in this plan.
  Rationale: The decision contract belongs to the portfolio stage and should be defined where it is introduced.
  Date/Author: 2026-05-26 / Codex
- Decision: Keep any rationale separate from the final contract.
  Rationale: The flow depends on a strict final value, but humans still need supporting reasoning for inspection and debugging.
  Date/Author: 2026-05-26 / Codex
- Decision: Add a narrow normalization or fallback parser if the model emits punctuation or extra prose.
  Rationale: The final contract is strict enough that small formatting drift should be corrected or rejected deterministically rather than silently passed through.
  Date/Author: 2026-05-26 / Codex
- Decision: Configure `portfolio_manager` with `llm_level: deep_llm`.
  Rationale: The portfolio manager makes the final decision and is the only plans 04-06 agent that should use the settings-backed deep model.
  Date/Author: 2026-06-05 / Codex
- Decision: Wire the portfolio stage into `TradingAgentsFlow` as part of this plan.
  Rationale: Plan 03 established that newly completed stages should be part of the main flow and saved as inspectable run artifacts.
  Date/Author: 2026-06-05 / Codex
- Decision (supersedes the 2026-05-26 contract entries): The portfolio crew's final output is the rich `PortfolioDecision` with a `rating` of `Buy`/`Overweight`/`Hold`/`Underweight`/`Sell`, plus `executive_summary`, `investment_thesis`, optional `price_target`, and optional `time_horizon`. There is no `approve`/`reject` word and no `reject` -> `Hold` flow remap.
  Rationale: `README.md` and `PROMPTS.md` are the canonical specifications and both define the rich rating contract. The earlier `approve`/`reject` plan predated the finalized `PROMPTS.md` spec. Aligning the plan to the canonical contract keeps the plan, README, and prompts consistent and lets `final_decision` use `output_pydantic=PortfolioDecision` directly.
  Date/Author: 2026-06-09 / Claude
- Decision: Implement the portfolio crew with two agents (`portfolio_manager`, `self_reflection_manager`) and two sequential tasks (`self_reflection`, `final_decision`).
  Rationale: `PROMPTS.md` "5. Portfolio Manager" defines exactly these agents and tasks. The crew runs self-reflection over past lessons first, then makes the final decision.
  Date/Author: 2026-06-09 / Claude
- Decision: `portfolio_manager` resolves to `deep_llm`; `self_reflection_manager` resolves to `quick_llm`.
  Rationale: `PROMPTS.md` states the deep model is used only for making the final decision, so the self-reflection role stays on the cheaper, faster quick model.
  Date/Author: 2026-06-09 / Claude
- Decision: Define `alpha_return = raw_return - benchmark_return`, with `benchmark_return` computed by the second return formula in `PROMPTS.md`.
  Rationale: The self-reflection prompt labels the figure "Alpha vs {benchmark_name}", which is the standard definition of alpha. `PROMPTS.md`'s prose is loose here, so the plan fixes the precise meaning.
  Date/Author: 2026-06-09 / Claude
- Decision: Persist lesson records in a per-instrument store and recompute realized returns lazily at the next decision time.
  Rationale: `PROMPTS.md` requires that, on the next decision for the same instrument, past records are updated with real returns and reflections before retrieval. A persistent store keyed by ticker is the simplest way to satisfy that requirement and keep the stage rerunnable.
  Date/Author: 2026-06-09 / Claude

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is a single runnable portfolio-stage helper that accepts the ticker, the research plan, the trader plan, and the risk debate, that updates and self-reflects on prior lesson records for that ticker, that retrieves up to `max_lessons` lessons as `{lessons_line}`, and that returns a structured `PortfolioDecision`. The stage should also persist a fresh lesson record for the current decision, be wired into `TradingAgentsFlow`, and be saved with the rest of the run outputs. Update this section after implementation and validation.

## Context and Orientation

By the time this plan starts, the repository should already contain the analyst stage from `plans/02_analyst_crew.md`, the research stage from `plans/03_research_crew.md`, the trader stage from `plans/04_trader_crew.md`, and the risk stage from `plans/05_risk_management_crew.md`. Extend the existing `TradingAgentsFlow` rather than adding a separate orchestration path.

Create a new directory:

    src/trading_agents/crews/portfolio_crew/

That directory should contain `portfolio_crew.py` and a `config/` folder with `agents.yaml` and `tasks.yaml`, matching the repository pattern used by other crews.

The portfolio crew is a one-person team modeled as two CrewAI agents:

- `portfolio_manager` makes the final decision (task `final_decision`) and uses the deep model.
- `self_reflection_manager` reflects on past decisions whose outcomes are now known (task `self_reflection`) and uses the quick model.

Key terms used below, defined in plain language:

- Lesson record: one stored row about a single past decision for one instrument. It holds the ticker, the trade date (the date the decision was made), the final decision recorded at that time, the raw return, the alpha return, the holding days, and the reflection. The reflection and the returns are filled in later, once the outcome is known.
- Benchmark: a market index used as a yardstick for the instrument. The benchmark for a ticker is resolved from the ticker's exchange suffix using this map (the empty suffix is the default for US-listed tickers):

        ".NS":  "^NSEI"        # NSE India (Nifty 50)
        ".BO":  "^BSESN"       # BSE India (Sensex)
        ".T":   "^N225"        # Tokyo (Nikkei 225)
        ".HK":  "^HSI"         # Hong Kong (Hang Seng)
        ".L":   "^FTSE"        # London (FTSE 100)
        ".TO":  "^GSPTSE"      # Toronto (TSX Composite)
        ".AX":  "^AXJO"        # Australia (ASX 200)
        ".SS":  "000001.SS"    # Shanghai (SSE Composite)
        ".SZ":  "399001.SZ"    # Shenzhen (SZSE Component)
        "":     "SPY"          # default for US-listed tickers (no suffix)

- Holding days: an integer capped at `max_holding_days` (default 5). For a lesson record whose trade date is `T`, count the transaction days (days with a CLOSE price) since `T` for the instrument and for the benchmark separately. If both already exceed `max_holding_days`, holding days is `max_holding_days`; otherwise holding days is the smaller of the two transaction-day counts. For example, if `T = 2026/06/04`, the latest CLOSE for the instrument is `2026/06/05` (1 transaction day) and for the benchmark is `2026/06/08` (2 transaction days, because `2026/06/06`-`2026/06/07` are a weekend), then holding days is 1.
- End date: the date that is exactly `holding days` transaction days after the trade date, computed separately for the instrument and the benchmark.
- Raw return: `(close[end_date] - close[trade_date]) / close[trade_date]` for the instrument.
- Benchmark return: the same close-to-close formula for the benchmark. If the benchmark has no CLOSE on the trade date, use the latest available previous date instead.
- Alpha return: `raw_return - benchmark_return`. Both raw and alpha returns are displayed in `+.1%` format (for example, `+2.3%`).
- `{lessons_line}`: the retrieved lessons fed into the final decision. After the steps below it is the list of up to `max_lessons` (default 30) lesson records for the instrument, or the literal string "You have not invested this instrument in the past yet." when no lesson record exists.

The self-reflection process for an instrument runs in this order before the final decision:

1. Update the instrument's existing lesson records with their realized returns (raw return, alpha return) and holding days.
2. Run the `self_reflection` task once per just-updated lesson record to produce a 2-4 sentence reflection.
3. Write each reflection back into its lesson record.
4. Retrieve up to `max_lessons` lesson records as `{lessons_line}` (or the fallback string when there are none).
5. Run the `final_decision` task using the investment plan, the trader plan, the risk debate history, and `{lessons_line}`, and persist a new lesson record for this decision.

## Plan of Work

First, extend `src/trading_agents/schemas.py`. Add the rich decision contract (the `PortfolioRating` scale is the one already shared with the Research Manager):

    class PortfolioDecision(BaseModel):
        rating: PortfolioRating
        executive_summary: str
        investment_thesis: str
        price_target: Optional[float] = None
        time_horizon: Optional[str] = None

Also add the lesson-record types. The exact field names are an implementation choice, but they must capture every field listed in the Context section:

    class LessonRecord(BaseModel):
        ticker: str
        trade_date: str
        final_decision: str
        raw_return: Optional[float] = None
        alpha_return: Optional[float] = None
        holding_days: Optional[int] = None
        reflection: Optional[str] = None

    class LessonBook(BaseModel):
        lessons: list[LessonRecord] = []

Second, implement the lesson store and return math, placing reusable constants (`max_lessons` default 30, `max_holding_days` default 5, and the benchmark map) in `src/trading_agents/config/settings.py` and exporting them from `trading_agents.config` rather than hard-coding them at call sites. The store persists lesson records per instrument (for example, as a JSON file under the run/output area keyed by ticker) and exposes helpers to: resolve the benchmark from a ticker suffix; compute holding days, raw return, benchmark return, and alpha return from price data using the existing data tools; update existing records; write reflections back; append a new record; and retrieve up to `max_lessons` records and render `{lessons_line}` (falling back to "You have not invested this instrument in the past yet." when empty).

Third, implement `src/trading_agents/crews/portfolio_crew/portfolio_crew.py`. Import and call `load_dotenv()` near the top of the module. Import `resolve_agent_config` from `trading_agents.config` and pass `config=resolve_agent_config(self.agents_config["portfolio_manager"])` and `config=resolve_agent_config(self.agents_config["self_reflection_manager"])` when constructing the two agents. Define `PortfolioCrew` with two agents named `portfolio_manager` and `self_reflection_manager` and two tasks named `self_reflection` and `final_decision`. Keep the crew sequential and traced (`tracing=True`). The `final_decision` task must use `output_pydantic=PortfolioDecision`.

Fourth, implement `run_portfolio_stage(inputs)`. That helper should validate the presence of `ticker`, `investment_plan`, `trader_plan`, and `risk_debate_history`; run the five-step self-reflection process described in the Context section; kick off the crew; and return at least:

    {
        "final_trade_decision": PortfolioDecision-as-dict,
        "lessons": [the lesson records retrieved as {lessons_line}],
    }

Parse the final crew output into `PortfolioDecision`. If CrewAI structured output drifts, preserve a human-readable copy separately and use a narrow normalization helper that maps trivial variants of the rating (for example `"Buy."` or `"BUY"`) to the canonical `PortfolioRating` value, or raises a clear error when the output is ambiguous.

Fifth, wire the portfolio stage into `src/trading_agents/main.py`. Import `run_portfolio_stage`, add `final_trade_decision` (the `PortfolioDecision`) and the retrieved `lessons` to `TradingAgentsState`, add a `@listen` method after the risk stage that passes `ticker`, `investment_plan`, `trader_plan`, and `risk_debate_history` into `run_portfolio_stage`, and persist the portfolio outputs with the other run artifacts (for example `final_trade_decision.md` and the updated lesson store). The flow-level final result is the `PortfolioDecision` itself; do not remap it.

Sixth, write the prompts in `src/trading_agents/crews/portfolio_crew/config/agents.yaml` and `src/trading_agents/crews/portfolio_crew/config/tasks.yaml`, following `PROMPTS.md` "5. Portfolio Manager" verbatim where it gives YAML. In `agents.yaml`, `self_reflection_manager` reviews its own past decision now that the outcome is known and writes exactly 2-4 sentences of plain prose; `portfolio_manager` synthesizes the risk analysts' debate and delivers the final decision, with `{lessons_line}` injected into its backstory under "Lessons from prior decisions and outcomes:". In `tasks.yaml`, `self_reflection` consumes `{raw_return}`, `{benchmark_name}`, `{alpha_return}`, and `{final_decision}` and is bound to `self_reflection_manager`; `final_decision` consumes `{ticker}`, `{investment_plan}`, `{trader_plan}`, and `{history}`, is bound to `portfolio_manager`, and emits the rating-scale decision. Both agent YAML blocks must use `llm_level` (`deep_llm` for `portfolio_manager`, `quick_llm` for `self_reflection_manager`), `allow_delegation: false`, and `verbose: true`; do not set a literal `llm`.

Seventh, add focused tests. Create:

    tests/test_portfolio_crew_config.py
    tests/test_portfolio_stage_contracts.py

The config test should verify method names, YAML keys, task-to-agent bindings (`self_reflection` -> `self_reflection_manager`, `final_decision` -> `portfolio_manager`), `llm_level: deep_llm` for `portfolio_manager`, `llm_level: quick_llm` for `self_reflection_manager`, and the absence of a literal `llm` in the agent YAML. The contract test should mock the final crew output to prove that `run_portfolio_stage` validates required inputs, returns a `PortfolioDecision` whose `rating` is one of the five allowed values, handles malformed model output according to the documented normalizer behavior, and exercises the lesson math: benchmark resolution from the ticker suffix, the holding-days cap example from the Context section, and `alpha_return = raw_return - benchmark_return`. Add a flow test that mocks `run_portfolio_stage` and proves `TradingAgentsFlow` passes upstream artifacts into the portfolio stage and persists the portfolio outputs.

Eighth, add a small smoke entry point only if needed, for example `src/trading_agents/dev_smoke_portfolio_stage.py`, that feeds local sample inputs into `run_portfolio_stage` and prints the resulting keys.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm the risk helper exists after plan 05:

       uv run python -c "from trading_agents.crews.risk_management_crew.risk_management_crew import run_risk_stage; print(run_risk_stage.__name__)"

2. Create the portfolio crew files if they do not exist yet:

       src/trading_agents/crews/portfolio_crew/portfolio_crew.py
       src/trading_agents/crews/portfolio_crew/config/agents.yaml
       src/trading_agents/crews/portfolio_crew/config/tasks.yaml

   The `agents.yaml` must define both `portfolio_manager` and `self_reflection_manager`; the `tasks.yaml` must define both `final_decision` and `self_reflection`. Update `src/trading_agents/main.py` in the same pass so the portfolio stage is part of `TradingAgentsFlow`.

3. Add the focused tests:

       tests/test_portfolio_crew_config.py
       tests/test_portfolio_stage_contracts.py

4. Run the portfolio-stage test suite:

       uv run pytest tests/test_portfolio_crew_config.py tests/test_portfolio_stage_contracts.py

   Expected success:

       passed

5. If a smoke helper is added, run it with local sample inputs:

       uv run python -m trading_agents.dev_smoke_portfolio_stage

   Expected behavior: the script prints that it produced `final_trade_decision` and the retrieved `lessons`.

## Validation and Acceptance

Acceptance requires all of the following behaviors:

- The new `portfolio_crew` package imports successfully.
- The crew exposes two agents (`portfolio_manager`, `self_reflection_manager`) and two tasks (`self_reflection`, `final_decision`), and the crew class resolves both agents through `resolve_agent_config()`.
- `portfolio_manager` uses `llm_level: deep_llm` and `self_reflection_manager` uses `llm_level: quick_llm`; neither agent YAML sets a literal `llm`.
- The YAML task `agent` values reference local agent keys that exist in `agents.yaml` (`self_reflection` -> `self_reflection_manager`, `final_decision` -> `portfolio_manager`).
- `run_portfolio_stage` rejects missing upstream artifacts (`ticker`, `investment_plan`, `trader_plan`, `risk_debate_history`) with a clear error before any live LLM work starts.
- The portfolio stage returns a `PortfolioDecision` whose `rating` is exactly one of `Buy`, `Overweight`, `Hold`, `Underweight`, or `Sell`.
- For an instrument with no prior lesson record, `{lessons_line}` is "You have not invested this instrument in the past yet."; for an instrument with prior records, the stage updates those records with realized returns and reflections and retrieves up to `max_lessons` of them.
- Benchmark resolution, the holding-days cap, and `alpha_return = raw_return - benchmark_return` behave as documented and are covered by tests.
- Normalizer behavior for malformed rating output is covered by tests and documented here.
- `TradingAgentsFlow` runs the portfolio stage after risk and stores and saves the portfolio outputs.
- Mocked tests pass without network or live LLM calls.

The normalizer test set must include at least malformed variants such as `Buy.` and `BUY because...` so the implementation documents whether they are normalized or rejected.

## Idempotence and Recovery

All work in this plan is additive. The portfolio helper can be rerun safely with the same mock inputs. The lesson store is keyed by instrument and trade date so reruns update existing records in place rather than duplicating them. If the model output drifts, adjust the narrow normalization helper and rerun focused tests without changing the downstream contract.

Revision Note: 2026-05-26 split the former combined plan 03 into a dedicated Portfolio Crew plan so the decision-stage work can proceed one crew at a time.

Revision Note: 2026-06-09 realigned the plan with the finalized `PROMPTS.md` "5. Portfolio Manager" specification after two commits added the self-reflection role and restricted deep-model use to the final decision. The plan now describes two agents (`portfolio_manager`, `self_reflection_manager`) and two tasks (`self_reflection`, `final_decision`), the lesson-record/self-reflection store with benchmark resolution and realized-return math, and `deep_llm` for the final decision with `quick_llm` for self-reflection. The earlier single-word `approve`/`reject` contract was superseded by the rich `PortfolioDecision` rating contract, which is the contract both `README.md` and `PROMPTS.md` define; the corresponding flow `reject` -> `Hold` remap was removed for the same reason. These changes were made to keep the plan, the README, and the prompts mutually consistent and to keep the plan self-contained for a novice implementer.
