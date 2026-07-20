from datetime import UTC, datetime, timedelta

import pytest
from crewai.hooks import get_before_llm_call_hooks

from trading_agents.evaluation.quota import (
    DailyQuotaReached,
    EvaluationQuotaLimiter,
    ModelQuota,
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
        policies={"gemini/test": ModelQuota(15, 450, 30)},
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
        policies={"gemini/test": ModelQuota(15, 450, 30)},
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
        policies={"gemini/test": ModelQuota(15, 2, 1)},
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
        policies={"gemini/test": ModelQuota(15, 2, 1)},
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


def test_limiter_applies_independent_model_rate_and_daily_limits(tmp_path):
    clock = FakeClock(datetime(2026, 7, 19, 8, tzinfo=UTC))
    limiter = EvaluationQuotaLimiter(
        tmp_path / "quota.json",
        policies={
            "gemini/quick": ModelQuota(15, 3, 1),
            "openai/deep": ModelQuota(60, 2, 1),
        },
        quota_timezone="America/Los_Angeles",
        now=clock.now,
        sleep=clock.sleep,
    )

    limiter.acquire("quick")
    limiter.acquire("quick")
    quick_delay = clock.sleeps[-1]
    limiter.acquire("deep")
    limiter.acquire("deep")
    deep_delay = clock.sleeps[-1]

    assert quick_delay >= 4.0
    assert 1.0 <= deep_delay < quick_delay
    assert limiter.remaining("gemini/quick") == 1
    assert limiter.remaining("openai/deep") == 0
    with pytest.raises(DailyQuotaReached) as raised:
        limiter.acquire("openai/deep")
    assert raised.value.model == "openai/deep"
    assert raised.value.used == 2
    assert limiter.remaining("gemini/quick") == 1


def test_limiter_rejects_ambiguous_normalized_model_aliases(tmp_path):
    with pytest.raises(ValueError, match="Ambiguous evaluation model alias"):
        EvaluationQuotaLimiter(
            tmp_path / "quota.json",
            policies={
                "gemini/shared": ModelQuota(15, 10, 1),
                "openai/shared": ModelQuota(60, 20, 1),
            },
            quota_timezone="UTC",
        )
