# TradingAgents

This project is a CrewAI-based reimplementation/replication of
[TradingAgents](https://github.com/TauricResearch/TradingAgents), the multi-agent
LLM financial trading framework proposed in the paper
*TradingAgents: Multi-Agents LLM Financial Trading Framework*.

## Project Goal

This project aims to reproduce the core ideas of
[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
using the [CrewAI](https://github.com/crewAIInc/crewAI) framework.

The original TradingAgents framework is a multi-agent LLM system for financial
trading research. It is inspired by the workflow of a real-world trading firm:
specialized analysts collect and interpret market information, researchers debate
bullish and bearish cases, a trader proposes an action, risk managers evaluate
the proposal, and a portfolio manager makes the final decision.

This repository is not a line-by-line port of the original implementation.
Instead, it maps the TradingAgents architecture into CrewAI concepts:

- **Agents**: role-specific LLM workers such as analysts, researchers, trader,
  risk managers, and portfolio manager.
- **Tasks**: concrete work items assigned to agents, such as generating a
  technical report, debating a bullish thesis, or validating portfolio risk.
- **Crews / Flows**: ordered collaboration pipelines that pass information from
  market analysis to final trade decision.
- **Tools**: data-retrieval and analysis utilities for prices, fundamentals,
  news, sentiment, technical indicators, and portfolio state.

## Conceptual Architecture

TradingAgents decomposes the trading decision process into several stages:

Market Data
   |
   v
Analyst Team
   |
   v
Research Team Debate
   |
   v
Trader Agent
   |
   v
Risk Management Team
   |
   v
Portfolio Manager
   |
   v
Final Decision

## Agents

Agents are implemented as Agent instances within respective crew classes, which are decorated by @CrewBase. Their roles, goals, and backstories are defined in a separate agents.yaml file placed under the src/trading_agents/crews/[crew name]/config folder. This is the folder for the crew that the agent belongs to.

The Analyst Crew is the exception to the one-upstream-agent-to-one-CrewAI-agent mapping. It now follows PROMPTS.md: one shared `analyst` agent performs the four analyst tasks sequentially, and tools are attached to tasks rather than to the agent. The upstream analyst URLs below are still prompt source material for the task descriptions and tool choices.

### 1. Analyst Team

The Analyst Team performs the first stage of information gathering and market
interpretation. In this CrewAI implementation, one shared Analyst agent produces
focused reports from four task-specific perspectives.

#### Fundamentals Analyst

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/fundamentals_analyst.py"

#### Sentiment Analyst

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/sentiment_analyst.py"

#### News Analyst

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/news_analyst.py"

#### Market Analyst

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/market_analyst.py"

### 2. Research Team

The Research Team consumes the Analyst Team reports and turns them into an
explicit debate. The goal is to prevent the system from blindly accepting one
interpretation of the data.

#### Bull Researcher

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/researchers/bull_researcher.py"

#### Bear Researcher

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/researchers/bear_researcher.py"

#### Research Manager

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/managers/research_manager.py"

### 3. Trader Agent

The Trader Agent synthesizes all prior reports and proposes a concrete trading
action.

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/trader/trader.py"

### 4. Risk Management Team

The Risk Management Team evaluates the Trader Agent's proposal from multiple
risk perspectives. Its purpose is to prevent attractive narratives from becoming
uncontrolled portfolio exposure.

#### Aggressive Risk Debator

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/aggressive_debator.py"

#### Conservative Risk Debator

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/conservative_debator.py"

#### Neutral Risk Debator

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/neutral_debator.py"

### 5. Portfolio Manager

The Portfolio Manager makes the final decision. This agent should not simply
repeat the Trader Agent's proposal. It should approve, reject, or modify the
trade based on the full chain of analysis and risk review.

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/managers/portfolio_manager.py"

## Tasks

Tasks are implemented as Task instances within respective crew classes, which are decorated by @CrewBase. Their description, expected output, and bound agent are defined in a separate tasks.yaml file placed under the src/trading_agents/crews/[crew name]/config folder. This is the folder for the crew that the task belongs to.

For the Analyst Crew, all four tasks bind to the same `analyst` agent. Tool access is configured in `analyst_crew.py` on each Task constructor so the shared agent can use different tools for market, sentiment, news, and fundamentals work.

### 1. Analyst Team

The Analyst Team performs the first stage of information gathering and market
interpretation. Four tasks are processed sequentially by one shared Analyst agent.

#### Market Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/market_analyst.py"

The output of this task is market report.

#### Sentiment Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/sentiment_analyst.py"

The output of this task is sentiment report.

#### News Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/news_analyst.py"

The output of this task is news report.

#### Fundamentals Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/fundamentals_analyst.py"

The output of this task is fundamentals report.

### 2. Research Team

The Research Team consumes the Analyst Team reports and turns them into an
explicit discussion. The bull research focused on bullish thesis, the bear research focused on bearish thesis take turn to convince the research manager, who is focused on the balance of both researches.  

#### Bull Research

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/researchers/bull_researcher.py"

The output of this task is bull response.

#### Bear Research

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/researchers/bear_researcher.py"

The output of this task is bear response.

#### Research Management

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/managers/research_manager.py"

The output of this task is investment plan.

### 3. Trader Agent - Transaction Proposal

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/trader/trader.py"

The output of this task is a trader plan structured as `TraderProposal`.

### 4. Risk Management Team

The Risk Management Team evaluates the Trader Agent's proposal from multiple
risk perspectives. The aggressive risk opinion focuses on opportunity cost and upside capture, the conservative risk opinion focuses on capital preservation, and the neutral risk opinion focuses on the balance. The debate takes turn to produce the whole debate history in all aspects.

#### Aggressive Risk Opinions

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/aggressive_debator.py"

The output of this task is aggressive response.

#### Conservative Risk Opinions

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/conservative_debator.py"

The output of this task is conservative response.

#### Neutral Risk Opinions

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/risk_mgmt/neutral_debator.py"

The output of this task is neutral response.

### 5. Portfolio Manager - Final Decision

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/managers/portfolio_manager.py"

The output of this task is final trade decision.

## Crews

Crews are implemented as crew classes, which are decorated by @CrewBase. All agents and tasks are defined as member functions, one function decorated with @agent for one agent and one function decorated with @task for one task. The crew itself is also defined as a member function decorated with @crew. Besides, two separate agents.yaml and tasks.yaml files placed under the src/trading_agents/crews/[crew name]/config folder defines the actual prompts and other information. 

The generated content_crew reference has been removed. Use the implemented src/trading_agents/crews/analyst_crew package as the current CrewAI wiring reference for this project.

### 1. Analyst Crew

This crew consists of one Analyst agent and four tasks, run sequentially:
- Analyst for Market Analysis
- Analyst for Sentiment Analysis
- Analyst for News Analysis
- Analyst for Fundamentals Analysis

Tools are bound to tasks rather than to the shared agent. Market Analysis gets price and indicator tools, Sentiment Analysis uses pre-fetched prompt blocks and no tools, News Analysis gets news tools, and Fundamentals Analysis gets fundamentals and financial-statement tools.

The input to this crew is:
- stock ticker
- current date

The Analyst Crew YAML uses `{current_date}` as the prompt date. The current flow trigger still accepts `trade_date` for compatibility and maps it to `current_date` before kicking off the crew. The crew derives `{end_date}` from `{current_date}` and derives `{start_date}` and `{sentiment_start_date}` as seven calendar days before `{current_date}`, matching the past-week language in the analyst prompts.

The outputs of this crew are:
- market report
- sentiment report
- news report
- fundamentals report

### 2. Research Crew

This crew consists of three agents and three tasks:
- Bull Researcher for Bull Research
- Bear Researcher for Bear Research
- Research Manager for Research Management

The research stage runs a fixed number of debate rounds. The default is one
round, configured by `research_stage.max_rounds` in runtime settings and
overridable with `TRADING_AGENTS_RESEARCH_STAGE__MAX_ROUNDS`.

For each debate round, the stage executes:
- bull research
- bear research

After all configured debate rounds are complete, the stage executes research
management once. The research manager receives the ticker and the final debate
history, but not the original analyst reports or the latest `current_response`,
and that single manager output becomes the stage investment plan. There is no
`HAS_MORE` stop signal; the debate ends when the configured round count is
reached.

The input to this crew is:
- ticker
- trade date
- fundamentals report
- sentiment report
- news report
- market report

The outputs of this crew are:
- debate history
- investment plan

The investment plan is structured with:
- recommendation
- rationale
- strategic actions

For each discussion iteration, the current discussion history and the previous
researcher's response are added to the bull or bear research input. The flow
prefixes researcher turns as `Bull Analyst:` and `Bear Analyst:` before
appending them to the debate history. The main flow saves the research outputs
to the run output directory as `debate_history.md` and `investment_plan.md`,
alongside the four analyst reports.

### 3. Trader Crew

This crew consists of one agent and one task:
- Trader Agent for `trader_decision`

The input to this crew is:
- ticker
- investment plan

The ticker must be used exactly as provided in every prompt, report, and
recommendation, preserving any exchange suffix such as `.TO`, `.L`, `.HK`, `.T`,
or `-USD`.

The outputs of this crew are:
- trader plan

The trader plan is structured as `TraderProposal` with:
- action: exactly one of `Buy`, `Hold`, or `Sell`
- reasoning: two to four sentences anchored in the analyst reports and research plan
- entry_price: optional entry target in the instrument's quote currency
- stop_loss: optional stop-loss price in the instrument's quote currency
- position_sizing: optional sizing guidance

The `trader_decision` task should use `output_pydantic=TraderProposal`.

### 4. Risk Management Crew

This crew consists of three agents and three tasks:
- Aggressive Risk Analyst for Aggressive Risk Opinions
- Conservative Risk Analyst for Conservative Risk Opinions
- Neutral Risk Analyst for Neutral Risk Opinions

The risk stage runs a fixed number of debate rounds. The default is one round,
configured by `risk_stage.max_rounds` in runtime settings and overridable with
`TRADING_AGENTS_RISK_STAGE__MAX_ROUNDS`. There is no `HAS_MORE` stop signal and
no per-agent skip rule; the debate ends only when the configured round count is
reached.

For each debate round, the stage executes:
- Aggressive Risk Opinions
- Conservative Risk Opinions
- Neutral Risk Opinions

The input to this crew is:
- fundamentals report
- sentiment report
- news report
- market report
- trader plan

The outputs of this crew are:
- risk debate history, including all risk debate opinions in sequence

For each debate iteration, the current debate history is added to the input. That is to say, within any debate iteration, the previous agent's output is added to the debate history and provided as input for the next agent's task.

### 5. Portfolio Crew

This crew consists of one agent and three tasks:
- Portfolio Manager for initial trade decision
- Portfolio Manager for self-reflection on the initial trade decision
- Portfolio Manager for final trade decision

The input to this crew is:
- investment plan
- trader plan
- risk debate history, including all risk debate opinions in sequence

The outputs of this crew are:
- final trade decision, which is exactly a single word, either "approve" or "reject"

## Flow

The flow consists of five crews in sequence:
- Analyst Crew
- Research Crew
- Trader Crew
- Risk Management Crew
- Portfolio Crew

The output of the flow is:
- "Hold", if the final trade decision of the Portfolio Crew is "reject"
- trader plan, the output of the Trader Crew, if the final trade decision of the Portfolio Crew is "approve"

# Installation

## Customizing

**Add your `OPENAI_API_KEY` into the `.env` file**

- Modify `src/trading_agents/main.py` to add custom inputs for your agents and tasks

## Running the Project

Run the default analyst flow with the default ticker and the current UTC trade date:

```bash
uv run analyze
```

Run the analyst flow for a specific ticker and save the reports under `output/<TICKER>_<TRADE_DATE>/`:

```bash
uv run analyze --ticker AAPL --trade-date 2026-05-25
```

If you omit `--trade-date`, the flow uses the current UTC date:

```bash
uv run analyze --ticker AAPL
```

The generated markdown reports are saved in the matching output directory, for example `output/AAPL_2026-05-25/`.

For compatibility, you can still pass a raw JSON trigger payload:

```bash
uv run run_with_trigger '{"ticker":"AAPL","trade_date":"2026-05-25"}'
```

# Acknowledgements and Citation

The original TradingAgents project was developed by Tauric Research and is
described in the following paper:

@misc{xiao2024tradingagents,
    title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
    author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
    year={2024},
    eprint={2412.20138},
    archivePrefix={arXiv},
    primaryClass={q-fin.TR}
}
