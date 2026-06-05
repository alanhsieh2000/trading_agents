from trading_agents.config.settings import (
    ANALYST_INPUT_OVERRIDE_KEYS,
    AnalystRuntimeConfig,
    ResearchStageSettings,
    get_settings,
    resolve_analyst_runtime_config,
)


def test_get_settings_uses_code_defaults(monkeypatch):
    monkeypatch.delenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", raising=False)
    monkeypatch.delenv("TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.news.ticker_limit == 20
    assert settings.news.global_limit == 10
    assert settings.news.global_lookback_days == 7
    assert settings.sentiment.stocktwits_limit == 30
    assert settings.sentiment.reddit_limit_per_sub == 5
    assert settings.analyst_stage.lookback_days == 7
    assert settings.research_stage.max_rounds == 1


def test_get_settings_honors_environment_overrides(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", "11")
    monkeypatch.setenv("TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS", "9")
    monkeypatch.setenv("TRADING_AGENTS_RESEARCH_STAGE__MAX_ROUNDS", "4")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.news.ticker_limit == 11
    assert settings.analyst_stage.lookback_days == 9
    assert settings.research_stage == ResearchStageSettings(max_rounds=4)


def test_resolve_analyst_runtime_config_prefers_per_run_overrides(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", "11")
    monkeypatch.setenv("TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS", "9")
    get_settings.cache_clear()

    runtime = resolve_analyst_runtime_config(
        {
            "lookback_days": 3,
            "news_limit": 4,
            "global_news_limit": 6,
            "stocktwits_limit": 7,
            "reddit_limit_per_sub": 2,
            "reddit_timeout": 1.5,
            "ignored_override": 999,
        }
    )

    assert runtime == AnalystRuntimeConfig(
        lookback_days=3,
        news_limit=4,
        global_news_limit=6,
        stocktwits_limit=7,
        reddit_limit_per_sub=2,
        reddit_timeout=1.5,
    )


def test_resolve_analyst_runtime_config_ignores_unknown_overrides(monkeypatch):
    monkeypatch.delenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", raising=False)
    get_settings.cache_clear()

    runtime = resolve_analyst_runtime_config({"unknown": 1})

    assert runtime.model_dump() == {
        "lookback_days": 7,
        "news_limit": 20,
        "global_news_limit": 10,
        "stocktwits_limit": 30,
        "reddit_limit_per_sub": 5,
        "reddit_timeout": 10.0,
    }


def test_override_allowlist_is_explicit_contract():
    assert ANALYST_INPUT_OVERRIDE_KEYS == (
        "lookback_days",
        "news_limit",
        "global_news_limit",
        "stocktwits_limit",
        "reddit_limit_per_sub",
        "reddit_timeout",
    )
