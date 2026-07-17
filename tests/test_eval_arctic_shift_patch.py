"""Tests for the targeted Arctic Shift evaluation dataset repair."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.error import HTTPError

import pytest

from trading_agents.config import get_settings
from trading_agents.evaluation import arctic_shift_patch
from trading_agents.evaluation.arctic_shift_patch import (
    ArcticShiftClient,
    ArcticShiftPage,
    ArcticShiftPost,
    ArcticShiftTimeout,
    apply_patch,
    fetch_arctic_shift_posts,
    render_reddit_payload,
)
from trading_agents.evaluation.dataset import EvalDataset


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _raw_post(
    post_id: str,
    subreddit: str = "wallstreetbets",
    created_at: str = "2026-01-02T12:00:00+00:00",
    *,
    score: int = 10,
    num_comments: int = 8,
) -> dict:
    return {
        "id": post_id,
        "created_utc": datetime.fromisoformat(created_at).timestamp(),
        "subreddit": subreddit,
        "title": f"Title {post_id}",
        "selftext": f"Body {post_id}",
        "score": score,
        "num_comments": num_comments,
    }


def _page(*posts: dict) -> ArcticShiftPage:
    content = json.dumps({"data": list(posts)}).encode()
    return ArcticShiftPage(content=content, data=posts)


def _post(
    post_id: str,
    created_at: str,
    *,
    subreddit: str = "wallstreetbets",
    score: int = 10,
    num_comments: int = 8,
) -> ArcticShiftPost:
    return ArcticShiftPost(
        post_id=post_id,
        ticker="GOOGL",
        subreddit=subreddit,
        created_at=datetime.fromisoformat(created_at),
        title=f"Title {post_id}",
        selftext=f"Body {post_id}",
        score=score,
        num_comments=num_comments,
    )


def test_client_builds_expected_query_and_waits_between_requests():
    calls = []
    sleeps = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps({"data": [_raw_post("abc")]}).encode()

    def fake_open(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeResponse()

    client = ArcticShiftClient(
        delay_seconds=1.0, timeout=4.0, opener=fake_open, sleep=sleeps.append
    )
    after = datetime(2025, 12, 19, tzinfo=timezone.utc)
    before = datetime(2026, 2, 14, tzinfo=timezone.utc)

    first = client.search(
        ticker="GOOGL", subreddit="wallstreetbets", after=after, before=before
    )
    client.search(ticker="GOOGL", subreddit="stocks", after=after, before=before)

    assert len(first.data) == 1
    assert "query=GOOGL" in calls[0][0]
    assert "limit=100" in calls[0][0]
    assert "fields=id%2Ccreated_utc%2Csubreddit" in calls[0][0]
    assert calls[0][1] == 4.0
    assert sleeps == [1.0]


def test_client_retries_429_using_reset_header_then_applies_normal_pacing():
    calls = 0
    sleeps = []
    headers = Message()
    headers["X-RateLimit-Reset"] = "5"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return b'{"data": []}'

    def fake_open(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(b"{}"),
            )
        return FakeResponse()

    client = ArcticShiftClient(opener=fake_open, sleep=sleeps.append)
    client.search(
        ticker="GOOGL",
        subreddit="stocks",
        after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        before=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert calls == 2
    assert sleeps == [6.0, 1.0]


def test_fetch_splits_timeout_and_deduplicates_overlapping_results(tmp_path):
    calls = []

    class FakeClient:
        limit = 100

        def search(self, *, ticker, subreddit, after, before):
            calls.append((after, before))
            if len(calls) == 1:
                raise ArcticShiftTimeout("split me")
            return _page(_raw_post("shared", subreddit=subreddit))

    posts, paths = fetch_arctic_shift_posts(
        ticker="GOOGL",
        subreddits=("wallstreetbets",),
        after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        before=datetime(2026, 1, 3, tzinfo=timezone.utc),
        raw_dir=tmp_path,
        client=FakeClient(),  # type: ignore[arg-type]
    )

    assert len(calls) == 3
    assert len(posts) == 1
    assert len(paths) == 2
    assert all(path.exists() for path in paths)


def test_fetch_splits_full_limit_page_instead_of_accepting_partial_data(tmp_path):
    calls = []

    class FakeClient:
        limit = 2

        def search(self, *, ticker, subreddit, after, before):
            calls.append((after, before))
            if len(calls) == 1:
                return _page(_raw_post("a"), _raw_post("b"))
            return _page(_raw_post(str(len(calls)), subreddit=subreddit))

    posts, paths = fetch_arctic_shift_posts(
        ticker="GOOGL",
        subreddits=("wallstreetbets",),
        after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        before=datetime(2026, 1, 3, tzinfo=timezone.utc),
        raw_dir=tmp_path,
        client=FakeClient(),  # type: ignore[arg-type]
    )

    assert len(calls) == 3
    assert {post.post_id for post in posts} == {"2", "3"}
    assert len(paths) == 3


def test_render_payload_matches_live_rich_format_and_excludes_future_posts():
    posts = [
        _post("older", "2026-01-01T12:00:00+00:00", score=7, num_comments=5),
        _post("newer", "2026-01-02T12:00:00+00:00", score=20, num_comments=12),
        _post("future", "2026-01-03T12:00:00+00:00"),
    ]

    payload = render_reddit_payload(
        "GOOGL",
        "2026-01-02",
        posts,
        subreddits=("wallstreetbets", "stocks"),
        lookback_days=7,
        limit_per_sub=5,
    )

    assert "r/wallstreetbets — 2 recent posts mentioning GOOGL:" in payload
    assert "[2026-01-02 ·   20↑ ·  12c] Title newer" in payload
    assert payload.index("Title newer") < payload.index("Title older")
    assert "Title future" not in payload
    assert payload.endswith(
        "r/stocks: <no posts found mentioning GOOGL in the past 7 days>"
    )


def test_render_payload_uses_upstream_message_when_all_subreddits_are_empty():
    payload = render_reddit_payload(
        "googl",
        "2026-01-02",
        [],
        subreddits=("wallstreetbets", "stocks", "investing"),
        lookback_days=7,
        limit_per_sub=5,
    )

    assert payload == (
        "<no Reddit posts found mentioning GOOGL across r/wallstreetbets, "
        "r/stocks, r/investing in the past 7 days>"
    )


def test_apply_patch_keeps_low_engagement_posts_and_replaces_only_exact_targets(
    monkeypatch, tmp_path
):
    dataset_path = tmp_path / "eval.duckdb"
    target_dates = [
        (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index))
        .date()
        .isoformat()
        for index in range(30)
    ]
    no_data = "No data available for Reddit posts for GOOGL."
    with EvalDataset(dataset_path) as dataset:
        for as_of_date in target_dates:
            dataset.put_tool_output("fetch_reddit_posts", "GOOGL", as_of_date, no_data)
        dataset.put_tool_output(
            "fetch_reddit_posts", "GOOGL", "2026-02-01", "UNCHANGED"
        )
        dataset.put_tool_output(
            "fetch_reddit_posts", "AAPL", "2026-01-01", "AAPL UNCHANGED"
        )

    posts = []
    for index, as_of_date in enumerate(target_dates):
        posts.append(_post(f"good-{index}", f"{as_of_date}T12:00:00+00:00"))
    posts.append(
        _post("low-quality", "2026-01-15T13:00:00+00:00", score=4, num_comments=99)
    )
    raw_file = tmp_path / "raw" / "page.json"
    raw_file.parent.mkdir()
    raw_file.write_text("{}")
    monkeypatch.setattr(
        arctic_shift_patch,
        "fetch_arctic_shift_posts",
        lambda **_kwargs: (posts, (raw_file,)),
    )

    result = apply_patch(
        dataset_path=dataset_path,
        ticker="GOOGL",
        after=datetime(2025, 12, 19, tzinfo=timezone.utc),
        before=datetime(2026, 2, 14, tzinfo=timezone.utc),
        raw_dir=tmp_path / "raw",
        delay_seconds=1,
        limit=100,
    )

    assert result.posts_fetched == 31
    assert result.payloads_replaced == 30
    assert result.backup_path is not None and result.backup_path.exists()
    with EvalDataset(dataset_path, read_only=True) as dataset:
        assert dataset.matching_tool_output_dates(
            "fetch_reddit_posts", "GOOGL", no_data
        ) == []
        assert (
            dataset.tool_output("fetch_reddit_posts", "GOOGL", "2026-02-01")
            == "UNCHANGED"
        )
        assert (
            dataset.tool_output("fetch_reddit_posts", "AAPL", "2026-01-01")
            == "AAPL UNCHANGED"
        )
        assert "low-quality" in dataset.tool_output(
            "fetch_reddit_posts", "GOOGL", "2026-01-15"
        )


def test_apply_patch_refuses_partial_target_set_before_fetch(monkeypatch, tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path) as dataset:
        dataset.put_tool_output(
            "fetch_reddit_posts",
            "GOOGL",
            "2026-01-02",
            "No data available for Reddit posts for GOOGL.",
        )
    monkeypatch.setattr(
        arctic_shift_patch,
        "fetch_arctic_shift_posts",
        lambda **_kwargs: pytest.fail("fetch should not run"),
    )

    with pytest.raises(RuntimeError, match="refusing a partial patch"):
        apply_patch(
            dataset_path=dataset_path,
            ticker="GOOGL",
            after=datetime(2025, 12, 19, tzinfo=timezone.utc),
            before=datetime(2026, 2, 14, tzinfo=timezone.utc),
            raw_dir=tmp_path / "raw",
            delay_seconds=1,
            limit=100,
        )


def test_apply_patch_is_idempotent_when_no_targets_remain(tmp_path):
    dataset_path = tmp_path / "eval.duckdb"
    with EvalDataset(dataset_path):
        pass

    result = apply_patch(
        dataset_path=dataset_path,
        ticker="GOOGL",
        after=datetime(2025, 12, 19, tzinfo=timezone.utc),
        before=datetime(2026, 2, 14, tzinfo=timezone.utc),
        raw_dir=tmp_path / "raw",
        delay_seconds=1,
        limit=100,
    )

    assert result.payloads_replaced == 0
    assert result.backup_path is None
