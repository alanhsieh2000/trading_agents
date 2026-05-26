# Runtime Settings Contract

Centralized runtime settings for the analyst/news/sentiment path live in `trading_agents.config.settings`.

## Resolution order

1. Per-run analyst input overrides for the explicit allowlist below
2. Environment variables
3. Typed code defaults

## Environment variables

- `TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS`
- `TRADING_AGENTS_NEWS__TICKER_LIMIT`
- `TRADING_AGENTS_NEWS__GLOBAL_LIMIT`
- `TRADING_AGENTS_NEWS__GLOBAL_LOOKBACK_DAYS`
- `TRADING_AGENTS_NEWS__GLOBAL_INDEX_SYMBOLS`
- `TRADING_AGENTS_SENTIMENT__STOCKTWITS_LIMIT`
- `TRADING_AGENTS_SENTIMENT__STOCKTWITS_TIMEOUT`
- `TRADING_AGENTS_SENTIMENT__REDDIT_SUBREDDITS`
- `TRADING_AGENTS_SENTIMENT__REDDIT_LIMIT_PER_SUB`
- `TRADING_AGENTS_SENTIMENT__REDDIT_TIMEOUT`
- `TRADING_AGENTS_SENTIMENT__REDDIT_INTER_REQUEST_DELAY`
- `TRADING_AGENTS_SENTIMENT__REDDIT_MIN_SCORE`
- `TRADING_AGENTS_SENTIMENT__REDDIT_MIN_COMMENTS`
- `TRADING_AGENTS_SENTIMENT__REDDIT_RECENCY_WINDOW_SECONDS`

## Per-run analyst override allowlist

Only these input keys are applied dynamically by `resolve_analyst_runtime_config()`:

- `lookback_days`
- `news_limit`
- `global_news_limit`
- `stocktwits_limit`
- `reddit_limit_per_sub`
- `reddit_timeout`

Unknown input keys are ignored by the runtime override resolver.
