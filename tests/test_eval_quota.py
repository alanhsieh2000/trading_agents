from datetime import UTC, datetime, timedelta

import pytest
from crewai.hooks import get_before_llm_call_hooks

from trading_agents.evaluation.quota import (
    DailyQuotaReached,
    EvaluationQuotaLimiter,
    evaluation_quota_hook,
)


class FakeClock:
    def __init__(self, value: datetime):
        self.value = value
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += timedelta(seconds=seconds)


def test_limiter_smooths_calls_and_persists_rolling_window(tmp_path):
    clock = FakeClock(datetime(2026, 7, 19, 8, tzinfo=UTC))
    path = tmp_path / "quota.json"
    limiter = EvaluationQuotaLimiter(
        path,
        models=["gemini/test"],
        max_rpm=15,
        daily_budget=450,
        quota_timezone="America/Los_Angeles",
        now=clock.now,
        sleep=clock.sleep,
    )

    for _ in range(16):
        limiter.acquire("gemini/test")

    assert limiter.remaining("gemini/test") == 434
    assert len(clock.sleeps) == 15
    assert all(delay >= 4.0 for delay in clock.sleeps)

    restored = EvaluationQuotaLimiter(
        path,
        models=["gemini/test"],
        max_rpm=15,
        daily_budget=450,
        quota_timezone="America/Los_Angeles",
        now=clock.now,
        sleep=clock.sleep,
    )
    assert restored.remaining("gemini/test") == 434
    assert restored.lifetime_count("gemini/test") == 16


def test_daily_budget_resets_at_midnight_pacific_but_lifetime_does_not(tmp_path):
    clock = FakeClock(datetime(2026, 7, 19, 6, 59, tzinfo=UTC))
    limiter = EvaluationQuotaLimiter(
        tmp_path / "quota.json",
        models=["gemini/test"],
        max_rpm=15,
        daily_budget=2,
        quota_timezone="America/Los_Angeles",
        now=clock.now,
        sleep=clock.sleep,
    )
    limiter.acquire("gemini/test")
    limiter.acquire("gemini/test")
    with pytest.raises(DailyQuotaReached):
        limiter.acquire("gemini/test")

    clock.value += timedelta(minutes=2)
    assert limiter.remaining("gemini/test") == 2
    limiter.acquire("gemini/test")
    assert limiter.remaining("gemini/test") == 1
    assert limiter.lifetime_count("gemini/test") == 3


def test_evaluation_hook_is_scoped_and_ignores_other_models(tmp_path):
    clock = FakeClock(datetime(2026, 7, 19, 8, tzinfo=UTC))
    limiter = EvaluationQuotaLimiter(
        tmp_path / "quota.json",
        models=["gemini/test"],
        max_rpm=15,
        daily_budget=2,
        quota_timezone="America/Los_Angeles",
        now=clock.now,
        sleep=clock.sleep,
    )
    before = get_before_llm_call_hooks()

    with evaluation_quota_hook(limiter):
        registered = get_before_llm_call_hooks()
        assert len(registered) == len(before) + 1
        limiter.hook(type("Context", (), {"llm": "openai/test"})())
        assert limiter.remaining("gemini/test") == 2
        normalized_llm = type("LLM", (), {"model": "test"})()
        limiter.hook(type("Context", (), {"llm": normalized_llm})())
        assert limiter.remaining("gemini/test") == 1

    assert get_before_llm_call_hooks() == before
