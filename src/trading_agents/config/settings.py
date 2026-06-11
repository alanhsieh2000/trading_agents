from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NewsSettings(BaseModel):
    ticker_limit: int = Field(default=20, ge=0)
    global_limit: int = Field(default=10, ge=0)
    global_lookback_days: int = Field(default=7, ge=0)
    global_index_symbols: tuple[str, ...] = ("^GSPC", "^IXIC", "^DJI")


class SentimentSettings(BaseModel):
    stocktwits_limit: int = Field(default=30, ge=0)
    stocktwits_timeout: float = Field(default=10.0, gt=0)
    reddit_subreddits: tuple[str, ...] = ("wallstreetbets", "stocks", "investing")
    reddit_limit_per_sub: int = Field(default=5, ge=0)
    reddit_timeout: float = Field(default=10.0, gt=0)
    reddit_inter_request_delay: float = Field(default=0.4, ge=0)
    reddit_min_score: int = Field(default=4)
    reddit_min_comments: int = Field(default=3)
    reddit_recency_window_seconds: int = Field(default=7 * 24 * 60 * 60, ge=0)


class AnalystStageSettings(BaseModel):
    lookback_days: int = Field(default=7, ge=0)


class ResearchStageSettings(BaseModel):
    max_rounds: int = Field(default=1, ge=1)


class RiskStageSettings(BaseModel):
    max_rounds: int = Field(default=1, ge=1)


class LLMSettings(BaseModel):
    quick_llm: str = Field(default="gpt-4o-mini", min_length=1)
    deep_llm: str = Field(default="gpt-4o-mini", min_length=1)


# Maps a ticker's exchange suffix to the benchmark index used as its yardstick.
# The empty suffix is the default for US-listed tickers (no suffix).
BENCHMARK_MAP: dict[str, str] = {
    ".NS": "^NSEI",       # NSE India (Nifty 50)
    ".BO": "^BSESN",      # BSE India (Sensex)
    ".T": "^N225",        # Tokyo (Nikkei 225)
    ".HK": "^HSI",        # Hong Kong (Hang Seng)
    ".L": "^FTSE",        # London (FTSE 100)
    ".TO": "^GSPTSE",     # Toronto (TSX Composite)
    ".AX": "^AXJO",       # Australia (ASX 200)
    ".SS": "000001.SS",   # Shanghai (SSE Composite)
    ".SZ": "399001.SZ",   # Shenzhen (SZSE Component)
    "": "SPY",            # default for US-listed tickers (no suffix)
}


class PortfolioStageSettings(BaseModel):
    max_lessons: int = Field(default=30, ge=0)
    max_holding_days: int = Field(default=5, ge=1)
    benchmark_map: dict[str, str] = Field(default_factory=lambda: dict(BENCHMARK_MAP))


class EvaluationSettings(BaseModel):
    """Settings for the 2024-Q1 cumulative-return backtest evaluation.

    When ``enabled`` is true, the analyst tools and the analyst stage's
    pre-fetched sentiment blocks read recorded payloads from the prepared
    DuckDB dataset at ``dataset_path`` instead of calling live APIs. See
    ``plans/07_evaluation_backtest.md``.
    """

    enabled: bool = False
    dataset_path: str = Field(default="data/eval_dataset.duckdb", min_length=1)
    tickers: tuple[str, ...] = ("AAPL", "GOOGL", "AMZN")
    benchmark: str = Field(default="SPY", min_length=1)
    start_date: str = Field(default="2024-01-01", min_length=1)
    end_date: str = Field(default="2024-03-29", min_length=1)
    buffer_start_date: str = Field(default="2023-12-01", min_length=1)
    # Extra calendar days of prices recorded past ``end_date`` so holding-window
    # returns can be computed for decisions late in the backtest window.
    price_tail_days: int = Field(default=14, ge=0)
    # Exchange-simulator constants from the README "Backtest" section.
    weight_over: float = Field(default=0.5, ge=0.0, le=1.0)
    weight_under: float = Field(default=0.5, ge=0.0, le=1.0)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADING_AGENTS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    news: NewsSettings = NewsSettings()
    sentiment: SentimentSettings = SentimentSettings()
    analyst_stage: AnalystStageSettings = AnalystStageSettings()
    research_stage: ResearchStageSettings = ResearchStageSettings()
    risk_stage: RiskStageSettings = RiskStageSettings()
    portfolio_stage: PortfolioStageSettings = PortfolioStageSettings()
    evaluation: EvaluationSettings = EvaluationSettings()
    llm: LLMSettings = LLMSettings()


ANALYST_INPUT_OVERRIDE_KEYS = (
    "lookback_days",
    "news_limit",
    "global_news_limit",
    "stocktwits_limit",
    "reddit_limit_per_sub",
    "reddit_timeout",
)


class AnalystRuntimeConfig(BaseModel):
    lookback_days: int = Field(ge=0)
    news_limit: int = Field(ge=0)
    global_news_limit: int = Field(ge=0)
    stocktwits_limit: int = Field(ge=0)
    reddit_limit_per_sub: int = Field(ge=0)
    reddit_timeout: float = Field(gt=0)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def resolve_agent_config(agent_config: Mapping[str, Any]) -> dict[str, Any]:
    resolved = dict(agent_config)
    llm_level = resolved.pop("llm_level", "quick_llm")
    llm_settings = get_settings().llm

    if llm_level == "quick_llm":
        resolved["llm"] = llm_settings.quick_llm
    elif llm_level == "deep_llm":
        resolved["llm"] = llm_settings.deep_llm
    else:
        raise ValueError(f"Unknown agent llm_level: {llm_level}")

    return resolved


def resolve_analyst_runtime_config(inputs: Mapping[str, Any]) -> AnalystRuntimeConfig:
    settings = get_settings()
    payload = {
        "lookback_days": settings.analyst_stage.lookback_days,
        "news_limit": settings.news.ticker_limit,
        "global_news_limit": settings.news.global_limit,
        "stocktwits_limit": settings.sentiment.stocktwits_limit,
        "reddit_limit_per_sub": settings.sentiment.reddit_limit_per_sub,
        "reddit_timeout": settings.sentiment.reddit_timeout,
    }
    for key in ANALYST_INPUT_OVERRIDE_KEYS:
        value = inputs.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        payload[key] = value
    return AnalystRuntimeConfig.model_validate(payload)
