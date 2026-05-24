# Implement Debate, Trader, Risk, and Portfolio Crews

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains `PLANS.md` at the project root. Maintain this document according to `PLANS.md`.

## Purpose / Big Picture

After this change, the project can turn the four analyst reports into a debated investment plan, a trader transaction proposal, a risk debate history, and a final approve-or-reject portfolio decision. A user should be able to see each decision stage separately and understand why the final decision was reached.

This plan implements the core TradingAgents decision chain after market analysis and before the final end-to-end flow.

## Progress

- [x] (2026-05-23 14:20Z) Read `README.md`, including the Research Crew, Trader Crew, Risk Management Crew, and Portfolio Crew requirements.
- [x] (2026-05-23 14:20Z) Reviewed upstream TradingAgents source summaries for bull, bear, research manager, trader, aggressive risk, conservative risk, neutral risk, and portfolio manager agents.
- [x] (2026-05-23 14:20Z) Read CrewAI skills for agent splitting, focused task design, context flow, structured output, and Flow orchestration tradeoffs.
- [ ] Ensure `plans/02_analyst_crew.md` has produced the four report outputs needed here.
- [ ] Add shared schemas for investment plans, trader plans, risk opinions, and final portfolio decisions.
- [ ] Implement `research_crew`.
- [ ] Implement `trader_crew`.
- [ ] Implement `risk_management_crew`.
- [ ] Implement `portfolio_crew`.
- [ ] Add mocked tests for each crew and for the stage-to-stage data contracts.
- [ ] Apply the runtime conventions proven in plan 02: import and call `load_dotenv()` before live runs, set every agent YAML entry to `llm: gpt-4o-mini`, and construct every Crew with `tracing=True`.

## Surprises & Discoveries

- Observation: `README.md` says the Trader Crew and Portfolio Crew each have one agent and three tasks, while the upstream TradingAgents source currently performs a single structured LLM call for those roles.
  Evidence: The README requires initial, self-reflection, and final tasks for each of Trader and Portfolio.
- Observation: The README line for Risk Management Crew appears to assign Conservative Risk Opinions to the Aggressive Risk Debator.
  Evidence: In the Risk Management Crew section, the second bullet repeats `Aggressive Risk Debator for Conservative Risk Opinions`; the surrounding text and upstream source clearly define a Conservative Risk Debator.
- Observation: The upstream Research Manager and Portfolio Manager use a five-level rating scale, but this project README requires the final Portfolio Crew output to be exactly `approve` or `reject`.
  Evidence: README says Portfolio Crew output is final trade decision, exactly a single word, either `approve` or `reject`.
- Observation: Plan 02 established project runtime conventions for future crews.
  Evidence: `analyst_crew.py` now imports `load_dotenv` and calls `load_dotenv()` before live kickoff, each analyst in `agents.yaml` uses `llm: gpt-4o-mini`, and all Crew instances are constructed with `tracing=True`.
- Observation: CrewAI tracing is configured on `Crew` or `Flow`, not on `Task`.
  Evidence: The official tracing docs show `Crew(..., tracing=True)` and `Flow(..., tracing=True)`, and local CrewAI 1.14.5 introspection found `tracing` on `Crew.model_fields` but not `Task.model_fields`.

## Decision Log

- Decision: Implement the README's three-task Trader and Portfolio crews rather than copying the upstream single-call structure exactly.
  Rationale: This project is a CrewAI reimplementation, and the README is the local product specification. The three-task shape also gives explicit self-reflection stages.
  Date/Author: 2026-05-23 / Codex
- Decision: Use a Conservative Risk Debator for Conservative Risk Opinions.
  Rationale: The README bullet is inconsistent with the role name, task title, and upstream source. Treat it as a typo and document the correction.
  Date/Author: 2026-05-23 / Codex
- Decision: Keep intermediate rich decision artifacts, but make the final Portfolio Crew result exactly `approve` or `reject`.
  Rationale: Rich reasoning is useful for auditability, while the end-to-end flow contract in README depends on a single-word final decision.
  Date/Author: 2026-05-23 / Codex
- Decision: Use `llm: gpt-4o-mini` in every new `agents.yaml` entry for research, trader, risk, and portfolio crews until a later plan changes the model.
  Rationale: This matches the analyst crew runtime setting and keeps model selection in YAML where CrewAI expects agent configuration.
  Date/Author: 2026-05-24 / Codex
- Decision: Import `load_dotenv` and call `load_dotenv()` at the top of every new crew module that can be run directly or in a live smoke.
  Rationale: Live stage helpers need `OPENAI_API_KEY` available before `Crew.kickoff()`, and plan 02 proved explicit dotenv loading works in this repository.
  Date/Author: 2026-05-24 / Codex
- Decision: Enable tracing with `tracing=True` on every Crew construction in this plan.
  Rationale: CrewAI tracing is a Crew/Flow setting, not a Task setting, and these decision-stage crews need trace visibility during live debugging.
  Date/Author: 2026-05-24 / Codex

## Outcomes & Retrospective

This plan is not implemented yet. The expected outcome is four CrewAI crew packages whose mocked runs can be chained from analyst reports to a portfolio decision. Update this section after implementation and after validation.

## Context and Orientation

This plan depends on `plans/02_analyst_crew.md`. The four analyst outputs are the inputs to the research and risk stages:

    fundamentals_report
    sentiment_report
    news_report
    market_report

Create these new directories:

    src/trading_agents/crews/research_crew/
    src/trading_agents/crews/trader_crew/
    src/trading_agents/crews/risk_management_crew/
    src/trading_agents/crews/portfolio_crew/

Each crew directory should contain a Python crew class and `config/agents.yaml` plus `config/tasks.yaml`, following the reference `content_crew` shape.

Definitions:

A debate history is a plain text transcript built by appending each participant's response in order. A self-reflection task asks the same agent to critique and improve its previous output before producing a final output. A structured output is a Pydantic model that downstream code can parse reliably rather than scraping free text.

## Plan of Work

First, add shared Pydantic models in `src/trading_agents/schemas.py`. Keep them small enough that LLMs can satisfy them:

    class InvestmentPlan(BaseModel):
        rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
        thesis: str
        supporting_evidence: list[str]
        key_risks: list[str]
        recommended_action: str

    class TraderPlan(BaseModel):
        action: Literal["BUY", "HOLD", "SELL"]
        rationale: str
        evidence_used: list[str]
        risk_controls: list[str]

    class RiskOpinion(BaseModel):
        speaker: Literal["Aggressive", "Conservative", "Neutral"]
        response: str
        has_more: bool = True

    class PortfolioDecision(BaseModel):
        decision: Literal["approve", "reject"]
        rationale: str

If CrewAI structured output is unreliable for a particular provider, keep a free-text fallback parser that extracts only the final single-word decision for Portfolio. Record any fallback behavior in this plan.

Second, implement `ResearchCrew`. It has agents:

- `bull_researcher`
- `bear_researcher`
- `research_manager`

It has tasks:

- `bull_research`
- `bear_research`
- `research_management`

The bull researcher argues for investing based on growth potential, competitive advantages, positive indicators, and direct rebuttals to the bear argument. The bear researcher argues against investing based on risks, competitive weaknesses, negative indicators, and direct rebuttals to the bull argument. The research manager evaluates the debate and produces an actionable `InvestmentPlan`.

The README requires several iterations until both researchers have no further responses or a maximum count is reached. Implement this with a stage helper, for example `run_research_stage(inputs, max_rounds=2)`, that loops:

1. Run bull research with analyst reports plus debate history.
2. Append bull output to debate history.
3. Run bear research with analyst reports plus debate history.
4. Append bear output to debate history.
5. If both participants signal no further response, stop.
6. Run research management to produce the latest investment plan.

To make stopping deterministic, add an output instruction to the bull and bear tasks: end with `HAS_MORE: yes` or `HAS_MORE: no`. Do not ask the model to return an empty response as the stop signal. Empty-response control is fragile and hard to test.

Third, implement `TraderCrew`. It has one agent:

- `trader_agent`

It has three tasks:

- `initial_trader_plan`
- `trader_self_reflection`
- `final_trader_plan`

The initial task turns the investment plan into a transaction proposal. The self-reflection task critiques whether the proposal is grounded in the analyst reports and research plan. The final task emits the final `TraderPlan`. The final trader plan should include `BUY`, `HOLD`, or `SELL`, concise rationale, evidence used, and risk controls. Preserve the upstream trader's intent: anchor the proposal in the analyst reports and research plan.

Fourth, implement `RiskManagementCrew`. It has agents:

- `aggressive_risk_debator`
- `conservative_risk_debator`
- `neutral_risk_debator`

It has tasks:

- `aggressive_risk_opinion`
- `conservative_risk_opinion`
- `neutral_risk_opinion`

The aggressive role champions high-reward opportunities and critiques excessive caution. The conservative role prioritizes capital preservation and points out downside risk. The neutral role balances both sides and challenges overconfidence or overcaution. Each opinion receives all four analyst reports, the trader plan, and current risk debate history.

Implement the README's skip logic in a helper such as `run_risk_stage(inputs, max_rounds=2)`. Use the same deterministic `HAS_MORE: yes/no` ending for each risk opinion. The helper should append each response to `risk_debate_history` in exact execution order and return the full transcript.

Fifth, implement `PortfolioCrew`. It has one agent:

- `portfolio_manager`

It has three tasks:

- `initial_trade_decision`
- `portfolio_self_reflection`
- `final_trade_decision`

The initial decision synthesizes the investment plan, trader plan, and risk debate. The self-reflection task critiques whether the decision overweights either opportunity or risk. The final decision emits exactly one lower-case word: `approve` or `reject`. Any rationale should be saved separately in state or task output, but the value passed to the final flow must be the exact single word.

## Concrete Steps

Run commands from `/app/trading_agents`.

1. Confirm analyst outputs are available through the helper from plan 02:

       uv run python -c "from trading_agents.crews.analyst_crew.analyst_crew import run_analyst_stage; print(run_analyst_stage)"

2. Create `src/trading_agents/schemas.py` with the small Pydantic models listed above.

3. Create the four crew directories and YAML files:

       src/trading_agents/crews/research_crew/research_crew.py
       src/trading_agents/crews/research_crew/config/agents.yaml
       src/trading_agents/crews/research_crew/config/tasks.yaml
       src/trading_agents/crews/trader_crew/trader_crew.py
       src/trading_agents/crews/trader_crew/config/agents.yaml
       src/trading_agents/crews/trader_crew/config/tasks.yaml
       src/trading_agents/crews/risk_management_crew/risk_management_crew.py
       src/trading_agents/crews/risk_management_crew/config/agents.yaml
       src/trading_agents/crews/risk_management_crew/config/tasks.yaml
       src/trading_agents/crews/portfolio_crew/portfolio_crew.py
       src/trading_agents/crews/portfolio_crew/config/agents.yaml
       src/trading_agents/crews/portfolio_crew/config/tasks.yaml

4. For each crew Python file, import `load_dotenv` from `dotenv` and call `load_dotenv()` near the top of the module before any live helper can call `Crew.kickoff()`. Every new `agents.yaml` entry must include `llm: gpt-4o-mini` unless the user explicitly changes the default model. Every `Crew(...)` created in this plan must include `tracing=True`; do not add `tracing` to `Task(...)` because CrewAI does not support that field.

For each crew Python file, follow the `ContentCrew` pattern:

       @CrewBase
       class ResearchCrew:
           agents_config = "config/agents.yaml"
           tasks_config = "config/tasks.yaml"

   Use `Process.sequential` for fixed task sequences. The iterative helper functions can call a crew or agent tasks repeatedly. Include `tracing=True` in the returned `Crew` constructor.

5. Add tests, for example:

       tests/test_decision_crews_config.py
       tests/test_decision_stage_contracts.py

   The config test should verify YAML keys and agent-task references. The contract test should use mocked LLM outputs to prove that:

   - Research stage returns `investment_plan`.
   - Trader stage returns `trader_plan`.
   - Risk stage returns `risk_debate_history`.
   - Portfolio stage returns exactly `approve` or `reject`.

6. Run:

       uv run pytest tests/test_decision_crews_config.py tests/test_decision_stage_contracts.py

   Expected success:

       passed

7. With valid `OPENAI_API_KEY`, run a mocked-data live LLM smoke test that starts from local sample analyst reports:

       uv run python -m trading_agents.dev_smoke_decision_chain

   If this helper does not exist yet, create it under `src/trading_agents/dev_smoke_decision_chain.py` and keep it small. It should print the final keys and the final decision.

## Validation and Acceptance

Acceptance requires:

- All four new crew packages import successfully.
- Each crew's YAML task `agent` field references a local agent key.
- The Research stage can produce an investment plan from four analyst report strings.
- The Trader stage can produce a final trader plan from an investment plan.
- The Risk stage can produce an ordered debate history from analyst reports plus trader plan.
- The Portfolio stage returns exactly `approve` or `reject`, lower-case, with no punctuation in the final decision value.
- Mocked tests pass without live LLM calls.

The final portfolio parser test should include bad model outputs like `Approve.` and `APPROVE because...`; it should normalize or reject them according to the chosen implementation and document that behavior here.

## Idempotence and Recovery

All crew additions are additive. If a helper loop fails mid-run, no destructive state should be written outside `output/`. If output files are added for debugging, write them under `output/debug/` and make them safe to overwrite.

If structured output fails with the configured model, use the free-text fallback and keep the Pydantic model for tests and future providers. Do not remove the final single-word Portfolio contract.

If a debate participant emits no `HAS_MORE` marker, treat it as `HAS_MORE: no` after one repair prompt or parser warning. Record repeated marker failures in `Surprises & Discoveries`.

## Artifacts and Notes

Upstream behavior summary used for planning:

- Bull researcher: argues for investment using growth potential, competitive advantages, positive indicators, and rebuttals to bear concerns.
- Bear researcher: argues against investment using risks, competitive weaknesses, negative indicators, and rebuttals to bull claims.
- Research manager: evaluates the debate and chooses a five-level stance: Buy, Overweight, Hold, Underweight, or Sell.
- Trader: turns the research manager's investment plan into a concrete buy, hold, or sell proposal.
- Aggressive risk debator: emphasizes upside capture and critiques caution as possible missed opportunity.
- Conservative risk debator: emphasizes asset protection, volatility control, and capital preservation.
- Neutral risk debator: balances aggressive and conservative arguments.
- Portfolio manager: synthesizes risk debate and proposal into the final decision.

Expected stage dictionary after this plan:

    {
        "investment_plan": "<structured or markdown investment plan>",
        "trader_plan": "<structured or markdown transaction proposal>",
        "risk_debate_history": "<ordered transcript>",
        "final_trade_decision": "approve"
    }

## Interfaces and Dependencies

At the end of this plan, these imports should work:

    from trading_agents.crews.research_crew.research_crew import ResearchCrew, run_research_stage
    from trading_agents.crews.trader_crew.trader_crew import TraderCrew, run_trader_stage
    from trading_agents.crews.risk_management_crew.risk_management_crew import RiskManagementCrew, run_risk_stage
    from trading_agents.crews.portfolio_crew.portfolio_crew import PortfolioCrew, run_portfolio_stage
    from trading_agents.schemas import InvestmentPlan, TraderPlan, RiskOpinion, PortfolioDecision

The stage helpers should accept and return dictionaries so `src/trading_agents/main.py` can compose them without knowing CrewAI internals.

Revision Note: 2026-05-23 14:20Z Initial ExecPlan drafted after reading the README decision-stage requirements, project-local CrewAI skills, and upstream TradingAgents agent behavior summaries. This plan resolves README/source differences explicitly.

Revision Note: 2026-05-24 06:57Z Added plan 02 runtime conventions to the unimplemented decision crews: explicit dotenv loading before live runs, `llm: gpt-4o-mini` in all agent YAML entries, and `tracing=True` on Crew construction rather than Task construction.
