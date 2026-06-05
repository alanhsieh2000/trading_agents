from trading_agents.config.settings import (
    ANALYST_INPUT_OVERRIDE_KEYS,
    AnalystRuntimeConfig,
    LLMSettings,
    ResearchStageSettings,
    get_settings,
    resolve_agent_config,
    resolve_analyst_runtime_config,
)


def test_get_settings_uses_code_defaults(monkeypatch):
    monkeypatch.delenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", raising=False)
    monkeypatch.delenv("TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS", raising=False)
    monkeypatch.delenv("TRADING_AGENTS_LLM__QUICK_LLM", raising=False)
    monkeypatch.delenv("TRADING_AGENTS_LLM__DEEP_LLM", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.news.ticker_limit == 20
    assert settings.news.global_limit == 10
    assert settings.news.global_lookback_days == 7
    assert settings.sentiment.stocktwits_limit == 30
    assert settings.sentiment.reddit_limit_per_sub == 5
    assert settings.analyst_stage.lookback_days == 7
    assert settings.research_stage.max_rounds == 1
    assert settings.llm == LLMSettings(
        quick_llm="gpt-4o-mini",
        deep_llm="gpt-4o-mini",
    )


def test_get_settings_honors_environment_overrides(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_NEWS__TICKER_LIMIT", "11")
    monkeypatch.setenv("TRADING_AGENTS_ANALYST_STAGE__LOOKBACK_DAYS", "9")
    monkeypatch.setenv("TRADING_AGENTS_RESEARCH_STAGE__MAX_ROUNDS", "4")
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "openai/gpt-4o-mini")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "openai/gpt-4o")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.news.ticker_limit == 11
    assert settings.analyst_stage.lookback_days == 9
    assert settings.research_stage == ResearchStageSettings(max_rounds=4)
    assert settings.llm == LLMSettings(
        quick_llm="openai/gpt-4o-mini",
        deep_llm="openai/gpt-4o",
    )


def test_resolve_agent_config_injects_quick_llm(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "quick-model")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "deep-model")
    get_settings.cache_clear()
    source = {"role": "role", "llm_level": "quick_llm", "verbose": True}

    resolved = resolve_agent_config(source)

    assert resolved == {"role": "role", "verbose": True, "llm": "quick-model"}
    assert source == {"role": "role", "llm_level": "quick_llm", "verbose": True}


def test_resolve_agent_config_injects_deep_llm(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "quick-model")
    monkeypatch.setenv("TRADING_AGENTS_LLM__DEEP_LLM", "deep-model")
    get_settings.cache_clear()

    resolved = resolve_agent_config({"role": "role", "llm_level": "deep_llm"})

    assert resolved["llm"] == "deep-model"


def test_resolve_agent_config_defaults_to_quick_llm(monkeypatch):
    monkeypatch.setenv("TRADING_AGENTS_LLM__QUICK_LLM", "quick-model")
    get_settings.cache_clear()

    resolved = resolve_agent_config({"role": "role"})

    assert resolved["llm"] == "quick-model"


def test_resolve_agent_config_rejects_unknown_llm_level():
    get_settings.cache_clear()

    try:
        resolve_agent_config({"llm_level": "unknown"})
    except ValueError as exc:
        assert str(exc) == "Unknown agent llm_level: unknown"
    else:
        raise AssertionError("Expected ValueError")


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
