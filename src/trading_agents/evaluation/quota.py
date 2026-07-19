"""Persistent, provider-wide request limiting for long evaluation runs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
from zoneinfo import ZoneInfo

from crewai.hooks import (
    register_before_llm_call_hook,
    unregister_before_llm_call_hook,
)


LEDGER_VERSION = 1
RPM_WINDOW = timedelta(seconds=60)
RPM_SAFETY_SECONDS = 0.25


class DailyQuotaReached(RuntimeError):
    """Raised before a provider call would exceed the evaluation daily budget."""


class EvaluationQuotaLimiter:
    """Limit and record all evaluation calls for one or more model identifiers."""

    def __init__(
        self,
        path: str | Path,
        *,
        models: Iterable[str],
        max_rpm: int,
        daily_budget: int,
        quota_timezone: str,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.path = Path(path)
        self.models = frozenset(str(model).strip() for model in models)
        self._model_aliases = {
            alias: model
            for model in self.models
            for alias in (model, model.split("/", 1)[-1])
        }
        self.max_rpm = max_rpm
        self.daily_budget = daily_budget
        self.quota_timezone = ZoneInfo(quota_timezone)
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._lock = threading.Lock()
        self._ledger = self._load()

    def acquire(self, model: str) -> None:
        """Wait for RPM capacity, then durably reserve one daily request."""
        normalized = self._canonical_model(model)
        if normalized is None:
            return

        while True:
            wait_seconds = 0.0
            with self._lock:
                now = self._utc_now()
                state = self._model_state(normalized, now)
                recent = self._recent_timestamps(state, now)
                state["request_timestamps"] = [stamp.isoformat() for stamp in recent]

                if int(state["daily_count"]) >= self.daily_budget:
                    raise DailyQuotaReached(
                        f"Daily evaluation request budget reached for {normalized}: "
                        f"{state['daily_count']}/{self.daily_budget}."
                    )

                if recent:
                    smooth_interval = 60.0 / self.max_rpm + RPM_SAFETY_SECONDS
                    wait_seconds = max(
                        wait_seconds,
                        smooth_interval - (now - recent[-1]).total_seconds(),
                    )
                if len(recent) >= self.max_rpm:
                    wait_seconds = max(
                        wait_seconds,
                        (recent[0] + RPM_WINDOW - now).total_seconds()
                        + RPM_SAFETY_SECONDS,
                    )

                if wait_seconds <= 0:
                    recent.append(now)
                    state["request_timestamps"] = [
                        stamp.isoformat() for stamp in recent
                    ]
                    state["daily_count"] = int(state["daily_count"]) + 1
                    state["lifetime_count"] = int(state["lifetime_count"]) + 1
                    self._write()
                    return

            self._sleep(wait_seconds)

    def remaining(self, model: str) -> int:
        """Return locally observable daily capacity for ``model``."""
        normalized = self._canonical_model(model) or str(model).strip()
        with self._lock:
            state = self._model_state(normalized, self._utc_now())
            self._write()
            return max(0, self.daily_budget - int(state["daily_count"]))

    def lifetime_count(self, model: str) -> int:
        normalized = self._canonical_model(model) or str(model).strip()
        with self._lock:
            state = self._model_state(normalized, self._utc_now())
            return int(state["lifetime_count"])

    def next_reset(self) -> datetime:
        local_now = self._utc_now().astimezone(self.quota_timezone)
        tomorrow = local_now.date() + timedelta(days=1)
        return datetime.combine(tomorrow, datetime.min.time(), self.quota_timezone)

    def hook(self, context: Any) -> None:
        self.acquire(_context_model(context))
        return None

    def _canonical_model(self, model: str) -> str | None:
        return self._model_aliases.get(str(model).strip())

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _model_state(self, model: str, now: datetime) -> dict[str, Any]:
        models = self._ledger.setdefault("models", {})
        state = models.setdefault(
            model,
            {
                "quota_date": "",
                "daily_count": 0,
                "lifetime_count": 0,
                "request_timestamps": [],
            },
        )
        quota_date = now.astimezone(self.quota_timezone).date().isoformat()
        if state.get("quota_date") != quota_date:
            state["quota_date"] = quota_date
            state["daily_count"] = 0
            state["request_timestamps"] = []
        return state

    def _recent_timestamps(
        self, state: dict[str, Any], now: datetime
    ) -> list[datetime]:
        cutoff = now - RPM_WINDOW
        parsed: list[datetime] = []
        for value in state.get("request_timestamps", []):
            try:
                stamp = datetime.fromisoformat(str(value)).astimezone(UTC)
            except (TypeError, ValueError):
                continue
            if stamp > cutoff:
                parsed.append(stamp)
        return sorted(parsed)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": LEDGER_VERSION, "models": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != LEDGER_VERSION:
            raise ValueError(f"Unsupported evaluation quota ledger: {self.path}")
        if not isinstance(payload.get("models"), dict):
            raise ValueError(f"Malformed evaluation quota ledger: {self.path}")
        return payload

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(self._ledger, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


@contextmanager
def evaluation_quota_hook(limiter: EvaluationQuotaLimiter):
    """Scope a global CrewAI hook to one evaluation invocation."""
    hook = limiter.hook
    register_before_llm_call_hook(hook)
    try:
        yield
    finally:
        unregister_before_llm_call_hook(hook)


def _context_model(context: Any) -> str:
    llm = getattr(context, "llm", None)
    model = getattr(llm, "model", llm)
    return str(model or "").strip()
