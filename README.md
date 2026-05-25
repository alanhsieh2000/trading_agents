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

In the below sub-sections, there is one URL for each agent. By reading it, we can extract:
- role
- goal
- backstory
- tools
and put them to respective agents.yaml. The project goal is to replicate the original work, so we must keep these prompts and tools as close to the original ones as possible, including tool names.

### 1. Analyst Team

The Analyst Team performs the first stage of information gathering and market
interpretation. Each analyst should produce a focused report from a specific
perspective.

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

Tasks are implemented as Task instances within respective crew classes, which are decorated by @CrewBase. Their description, expected output, and bond agent are defined in a separate tasks.yaml file placed under the src/trading_agents/crews/[crew name]/config folder. This is the folder for the crew that the agent belongs to. 

In the below sub-sections, there is one URL for each agent. By reading it, we can extract:
- description
- expected_output
- agent
and put them to respective tasks.yaml. The project goal is to replicate the original work, so we must keep these prompts as close to the original ones as possible. The name of the agent should be exactly the same as the bond agent defined in the agents.yaml in the same folder.

### 1. Analyst Team

The Analyst Team performs the first stage of information gathering and market
interpretation. Four tasks are processed in parallel by four agents.

#### Fundamentals Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/fundamentals_analyst.py"

The output of this task is fundamentals report.

#### Sentiment Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/sentiment_analyst.py"

The output of this task is sentiment report.

#### News Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/news_analyst.py"

The output of this task is news report.

#### Market Analysis

Read "https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/analysts/market_analyst.py"

The output of this task is market report.

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

The output of this task is trader plan.

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

This crew consists of four agents and four tasks:
- Fundamentals Analyst for Fundamentals Analysis
- Sentiment Analyst for Sentiment Analysis
- News Analyst for News Analysis
- Market Analyst for Market Analysis

These four agents can do their task in parallel.

The input to this crew is:
- stock ticker
- date

The outputs of this crew are:
- fundamentals report
- sentiment report
- news report
- market report

### 2. Research Crew

This crew consists of three agents and three tasks:
- Bull Researcher for Bul Research
- Bear Researcher for Bear Research
- Research Manager for Research Management

The three agents do their tasks in sequence for several iterations until both researchers have no further responses or the count reaches the maximum:
- bull research
- bear research
- research management, skipped if both researcher have no further responses

The input to this crew is:
- fundamentals report
- sentiment report
- news report
- market report

The outputs of this crew are:
- investment plan

For each discussion iteration, the current discussion history is added to the input. That is to say, within any discussion iteration, the previous agent's output is added to the discussion history and provided as input for the next agent's task.

### 3. Trader Crew

This crew consists of one agent and three tasks:
- Trader Agent for initial trader plan
- Trader Agent for self-reflection on the initial trader plan
- Trader Agent for final trader plan

The input to this crew is:
- investment plan

The outputs of this crew are:
- trader plan

### 4. Risk Management Crew

This crew consists of three agents and three tasks:
- Aggressive Risk Debator for Aggressive Risk Opinions
- Aggressive Risk Debator for Conservative Risk Opinions
- Neutral Risk Debator for Neutral Risk Opinions

The three agents do their tasks in sequence for several iterations until all debators have no further responses or the count reaches the maximum:
- Aggressive Risk Opinions, skipped if the other two debators have no further respones in the previous iteration
- Conservative Risk Opinions, skipped if aggressive risk debator has no further response in the current iteration and neutral risk debator has no further respone in the previous iteration
- Neutral Risk Opinions, skipped if the other two debators have no further responses in the current iteration

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

## Prompting

In the CrewAI framework, prompts are controlled by:
- agents
    - role
    - goal
    - backstory
- tasks
    - description
    - expected_output
    - markdown

### System Prompt

The system prompt is in this format:
```written in agents.yaml
You are {role}
. {backstory}

Your personal goal is: {goal}
```

### User Prompt

The user prompt is in this format:
```written in tasks.yaml
Current task: {description}


This is the expected criteria for your final answer: {expected_output}
# add the following lines if {markdown} is true

you MUST return the actual complete content as the final answer, not a summary.
Your final answer MUST be formatted in Markdown syntax.
Follow these guidelines:
- Use # for headers
- Use ** for bold text
- Use * for italic text
- Use - or * for bullet points
- Use `code` for inline code
- Use ```language for code blocks
```

### 1. Analyst Team

In the original implementation, all four analysts share a common part of their system prompts at the beginning of the system prompt. For convinience, it is named {analyst} within this section and all sub-sections of this section.

```{analyst_beginning}
You are a helpful AI assistant, collaborating with other assistants. Use the provided tools to progress towards answering the question. If you are unable to fully answer, that's OK; another assistant with different tools will help where you left off. Execute what you can to make progress. If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable, prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop.
```

Additionally, all four analysts also share a common part of their system prompts at the ending of the system prompt. For convinience, it is named {analyst_ending} within this section and all sub-sections of this section.

```{analyst_ending}
For your reference, the current date is {current_date}. The instrument to analyze is {ticker}. Use this exact ticker in every tool call, report, and recommendation, preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`).
```

In the original implementation, analysts are working in this sequence:
- Market Analyst
- Sentiment Analyst
- News Analyst
- Fundamentals Analyst

The first one, the Market Analyst gets this user prompt:
{ticker}
or,
{company_name}

The others gets only a single word for the user prompt:
Continue

As we can see, the original implementation of the Analyst Team works like four specialized analysts working on the same task. To transform the original implementation into a CrewAI framework based implementation, we want to decompose the original heavy system prompt into balanced system and user prompts. The way we choose is to use a single Analyst agent who can do market, sentiment, news, and fundamentals analysis tasks sequencially as an analyst crew. Tools will be bond to tasks rather than the single agent.

#### Analyst

The Analyst is the single angent in the crew. The role, goal, and backstory are:

```agents.yaml
analyst:
  role: >
    a helpful AI assistant, collaborating with other assistants.
  goal: >
    Use the provided tools to progress towards answering the question. Execute what you can to make progress. If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable, prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop. The instrument to analyze is {ticker}. Use this exact ticker in every tool call, report, and recommendation, preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`).
  backstory: >
    If you are unable to fully answer, that's OK; another assistant with different tools will help where you left off. For your reference, the current date is {current_date}.
```

#### Market Analysis

The original implementation use this system prompt:

```The original system prompt
{analyst_beginning} You have access to the following tools: get_stock_data,
get_indicators.

You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.

{analyst_ending}
```

The description and expected output becomes:

```within tasks.yaml
market_analysis:
  name: market_analysis
  description: |
    You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

    Moving Averages:
    - close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
    - close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
    - close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

    MACD Related:
    - macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
    - macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
    - macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

    Momentum Indicators:
    - rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

    Volatility Indicators:
    - boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
    - boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
    - boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
    - atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

    Volume-Based Indicators:
    - vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

    Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names.
  expected_output: >
    Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.
  agent: analyst
  markdown: true
```

#### Sentiment Analysis

The original implementation use this system prompt:

```The original system prompt
{analyst_beginning}

You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this caveat explicitly. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output

Produce a sentiment report covering, in order:

1. **Overall sentiment direction** — Bullish / Bearish / Neutral / Mixed — with a brief confidence note based on data quality and sample size.
2. **Source-by-source breakdown** — what each of news / StockTwits / Reddit is telling you, with specific evidence (cite message counts, ratios, notable posts).
3. **Divergences, alignments, and key narratives** across sources.
4. **Catalysts and risks** surfaced by the data.
5. **Markdown table** at the end summarizing key sentiment signals, their direction, source, and supporting evidence.

{analyst_ending}
```

The description and expected output becomes:

```within tasks.yaml
sentiment_analysis:
  name: sentiment_analysis
  description: |
    You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

    ## Data sources (pre-fetched, in this prompt)

    ### News headlines — Yahoo Finance, past 7 days
    Institutional framing. Fact-driven, slower-moving signal.

    <start_of_news>
    {news_block}
    <end_of_news>

    ### StockTwits messages — retail-trader social platform indexed by cashtag
    Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

    <start_of_stocktwits>
    {stocktwits_block}
    <end_of_stocktwits>

    ### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
    Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

    <start_of_reddit>
    {reddit_block}
    <end_of_reddit>

    ## How to analyze this data (best practices)

    1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

    2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

    3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

    4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

    5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

    6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this caveat explicitly. If the sources are silent on a given subreddit, say so.

    7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

    8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.
  expected_output: |
    Produce a sentiment report covering, in order:
    1. **Overall sentiment direction** — Bullish / Bearish / Neutral / Mixed — with a brief confidence note based on data quality and sample size.
    2. **Source-by-source breakdown** — what each of news / StockTwits / Reddit is telling you, with specific evidence (cite message counts, ratios, notable posts).
    3. **Divergences, alignments, and key narratives** across sources.
    4. **Catalysts and risks** surfaced by the data.
    5. **Markdown table** at the end summarizing key sentiment signals, their direction, source, and supporting evidence.
  agent: analyst
  markdown: true
```

#### News Analysis

The original implementation use this system prompt:

```The original system prompt
{analyst_beginning} You have access to the following tools: get_news, get_global_news.

You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.

{analyst_ending}
```

The description and expected output becomes:

```within tasks.yaml
news_analysis:
  name: news_analysis
  description: >
    You are a news researcher tasked with analyzing recent news and trends over the past week. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news.
  expected_output: >
    Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.
  agent: analyst
  markdown: true
```

#### Fundamentals Analysis

The original implementation use this system prompt:

```The original system prompt
{analyst_beginning} You have access to the following tools: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement.

You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read. Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements.

{analyst_ending}
```

The description and expected output becomes:

```within tasks.yaml
fundamentals_analysis:
  name: fundamentals_analysis
  description: >
    You are a researcher tasked with analyzing fundamental information over the past week about a company. Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements.
  expected_output: >
    Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.
  agent: analyst
  markdown: true
```

# Installation

## Customizing

**Add your `OPENAI_API_KEY` into the `.env` file**

- Modify `src/trading_agents/main.py` to add custom inputs for your agents and tasks

## Running the Project

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