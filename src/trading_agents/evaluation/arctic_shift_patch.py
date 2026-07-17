"""Targeted Arctic Shift repair for missing historical Reddit replay payloads."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_agents.config import get_settings
from trading_agents.evaluation.dataset import EvalDataset


ARCTIC_SHIFT_SEARCH_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
DEFAULT_DATASET_PATH = "data/eval_dataset_2026q1.duckdb"
DEFAULT_RAW_DIR = Path("data/raw-backtest/arctic-shift")
DEFAULT_AFTER = "2025-12-19"
DEFAULT_BEFORE = "2026-02-14"
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_LIMIT = 100
EXPECTED_AFFECTED_COUNT = 30
MAX_RATE_LIMIT_RETRIES = 3
INITIAL_SLICE = timedelta(days=7)
MINIMUM_SLICE = timedelta(hours=1)
FIELDS = (
    "id",
    "created_utc",
    "subreddit",
    "title",
    "selftext",
    "score",
    "num_comments",
)
ARCTIC_SHIFT_HEADERS = {
    "User-Agent": "curl/8.0 tradingagents-arctic-shift-patch/1.0",
    "Accept": "application/json",
}


class ArcticShiftTimeout(RuntimeError):
    """Arctic Shift could not search the requested time slice."""


@dataclass(frozen=True)
class ArcticShiftPost:
    post_id: str
    ticker: str
    subreddit: str
    created_at: datetime
    title: str
    selftext: str
    score: int
    num_comments: int


@dataclass(frozen=True)
class ArcticShiftPage:
    content: bytes
    data: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class PatchResult:
    ticker: str
    posts_fetched: int
    payloads_replaced: int
    raw_files_written: int
    backup_path: Path | None


class ArcticShiftClient:
    """Small paced client with bounded rate-limit retries."""

    def __init__(
        self,
        *,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        timeout: float = 30.0,
        limit: int = DEFAULT_LIMIT,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.delay_seconds = max(delay_seconds, 0.0)
        self.timeout = timeout
        self.limit = min(max(limit, 1), 100)
        self._opener = opener
        self._sleep = sleep
        self._made_request = False

    def search(
        self,
        *,
        ticker: str,
        subreddit: str,
        after: datetime,
        before: datetime,
    ) -> ArcticShiftPage:
        params = {
            "subreddit": subreddit,
            "query": ticker,
            "after": _format_api_datetime(after),
            "before": _format_api_datetime(before),
            "sort": "asc",
            "limit": self.limit,
            "fields": ",".join(FIELDS),
        }
        request = Request(
            f"{ARCTIC_SHIFT_SEARCH_URL}?{urlencode(params)}",
            headers=ARCTIC_SHIFT_HEADERS,
        )
        retries = 0
        while True:
            self._pace()
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    content = response.read()
                return _parse_page(content)
            except HTTPError as exc:
                if exc.code == 422:
                    raise ArcticShiftTimeout(
                        f"Arctic Shift timed out for r/{subreddit} "
                        f"{params['after']}..{params['before']}"
                    ) from exc
                if exc.code != 429 or retries >= MAX_RATE_LIMIT_RETRIES:
                    raise RuntimeError(
                        f"Arctic Shift returned HTTP {exc.code} for r/{subreddit}"
                    ) from exc
                retries += 1
                self._sleep(_rate_limit_wait_seconds(exc.headers))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(f"Arctic Shift request failed for r/{subreddit}") from exc

    def _pace(self) -> None:
        if self._made_request and self.delay_seconds > 0:
            self._sleep(self.delay_seconds)
        self._made_request = True


def fetch_arctic_shift_posts(
    *,
    ticker: str,
    subreddits: Sequence[str],
    after: datetime,
    before: datetime,
    raw_dir: Path,
    client: ArcticShiftClient,
) -> tuple[list[ArcticShiftPost], tuple[Path, ...]]:
    """Fetch complete bounded slices and preserve every successful response."""
    posts_by_id: dict[str, ArcticShiftPost] = {}
    files_written: list[Path] = []
    for subreddit in subreddits:
        pending = list(reversed(_initial_slices(after, before)))
        while pending:
            slice_after, slice_before = pending.pop()
            try:
                page = client.search(
                    ticker=ticker,
                    subreddit=subreddit,
                    after=slice_after,
                    before=slice_before,
                )
            except ArcticShiftTimeout:
                pending.extend(
                    reversed(_split_slice(slice_after, slice_before, subreddit))
                )
                continue

            raw_path = _next_raw_path(raw_dir, ticker, subreddit)
            _write_bytes_atomic(raw_path, page.content)
            files_written.append(raw_path)
            if len(page.data) >= client.limit:
                pending.extend(
                    reversed(_split_slice(slice_after, slice_before, subreddit))
                )
                continue
            for item in page.data:
                post = _parse_post(item, ticker=ticker, expected_subreddit=subreddit)
                posts_by_id.setdefault(post.post_id, post)

    posts = sorted(posts_by_id.values(), key=lambda post: post.created_at)
    return posts, tuple(files_written)


def render_reddit_payload(
    ticker: str,
    as_of_date: str,
    posts: Sequence[ArcticShiftPost],
    *,
    subreddits: Sequence[str],
    lookback_days: int,
    limit_per_sub: int,
) -> str:
    """Render Arctic Shift data in the live Reddit helper's rich format."""
    symbol = ticker.upper().strip()
    end_date = date.fromisoformat(as_of_date)
    start_date = end_date - timedelta(days=lookback_days)
    blocks: list[str] = []
    total_posts = 0

    for subreddit in subreddits:
        selected = sorted(
            (
                post
                for post in posts
                if post.ticker == symbol
                and post.subreddit == subreddit
                and start_date <= post.created_at.date() <= end_date
            ),
            key=lambda post: post.created_at,
            reverse=True,
        )[: max(limit_per_sub, 0)]
        total_posts += len(selected)
        if not selected:
            blocks.append(
                f"r/{subreddit}: <no posts found mentioning "
                f"{symbol} in the past 7 days>"
            )
            continue

        lines = [f"r/{subreddit} — {len(selected)} recent posts mentioning {symbol}:"]
        for post in selected:
            created = post.created_at.date().isoformat()
            meta = f"{created} · {post.score:>4}↑ · {post.num_comments:>3}c"
            title = _one_line(post.title)
            selftext = _trim_text(_one_line(post.selftext), 240)
            lines.append(
                f" [{meta}] {title}"
                + (f"\n body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        subreddit_names = ", ".join(f"r/{subreddit}" for subreddit in subreddits)
        return (
            f"<no Reddit posts found mentioning {symbol} across "
            f"{subreddit_names} in the past 7 days>"
        )
    return "\n\n".join(blocks)


def apply_patch(
    *,
    dataset_path: Path,
    ticker: str,
    after: datetime,
    before: datetime,
    raw_dir: Path,
    delay_seconds: float,
    limit: int,
    client: ArcticShiftClient | None = None,
) -> PatchResult:
    symbol = ticker.upper().strip()
    no_data_payload = f"No data available for Reddit posts for {symbol}."
    with EvalDataset(dataset_path, read_only=True) as dataset:
        target_dates = dataset.matching_tool_output_dates(
            "fetch_reddit_posts", symbol, no_data_payload
        )
    if not target_dates:
        return PatchResult(symbol, 0, 0, 0, None)
    if len(target_dates) != EXPECTED_AFFECTED_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_AFFECTED_COUNT} affected rows for {symbol}, "
            f"found {len(target_dates)}; refusing a partial patch"
        )

    settings = get_settings().sentiment
    subreddits = tuple(settings.reddit_subreddits)
    client = client or ArcticShiftClient(
        delay_seconds=delay_seconds,
        limit=limit,
    )
    posts, raw_files = fetch_arctic_shift_posts(
        ticker=symbol,
        subreddits=subreddits,
        after=after,
        before=before,
        raw_dir=raw_dir,
        client=client,
    )
    replacements = {
        as_of_date: render_reddit_payload(
            symbol,
            as_of_date,
            posts,
            subreddits=subreddits,
            lookback_days=get_settings().analyst_stage.lookback_days,
            limit_per_sub=settings.reddit_limit_per_sub,
        )
        for as_of_date in target_dates
    }
    empty_payload = (
        f"<no Reddit posts found mentioning {symbol} across "
        f"{', '.join(f'r/{subreddit}' for subreddit in subreddits)} "
        "in the past 7 days>"
    )
    empty_dates = [
        as_of_date
        for as_of_date, payload in replacements.items()
        if payload == empty_payload
    ]
    if empty_dates:
        raise RuntimeError(
            "Arctic Shift data did not cover affected dates: " + ", ".join(empty_dates)
        )

    backup_path = dataset_path.with_suffix(dataset_path.suffix + ".pre-arctic-shift.bak")
    if not backup_path.exists():
        shutil.copy2(dataset_path, backup_path)
    with EvalDataset(dataset_path) as dataset:
        replaced = dataset.replace_matching_tool_outputs(
            "fetch_reddit_posts",
            symbol,
            replacements,
            expected_payload=no_data_payload,
        )
    return PatchResult(
        ticker=symbol,
        posts_fetched=len(posts),
        payloads_replaced=replaced,
        raw_files_written=len(raw_files),
        backup_path=backup_path,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch missing evaluation Reddit payloads through Arctic Shift."
    )
    parser.add_argument("--dataset-path", default=DEFAULT_DATASET_PATH)
    parser.add_argument("--ticker", default="GOOGL")
    parser.add_argument("--after", default=DEFAULT_AFTER)
    parser.add_argument("--before", default=DEFAULT_BEFORE)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    after = _parse_bound(args.after)
    before = _parse_bound(args.before)
    if after >= before:
        raise ValueError("--after must be earlier than --before")
    result = apply_patch(
        dataset_path=Path(args.dataset_path),
        ticker=args.ticker,
        after=after,
        before=before,
        raw_dir=Path(args.raw_dir),
        delay_seconds=max(args.delay, 0.0),
        limit=min(max(args.limit, 1), 100),
    )
    if result.payloads_replaced == 0:
        print(f"Arctic Shift patch already applied for {result.ticker}; no rows changed.")
        return 0
    print(
        "\n".join(
            [
                f"Arctic Shift Reddit patch applied for {result.ticker}",
                f"posts_fetched: {result.posts_fetched}",
                f"raw_files_written: {result.raw_files_written}",
                f"payloads_replaced: {result.payloads_replaced}",
                f"backup_path: {result.backup_path}",
            ]
        )
    )
    return 0


def _parse_page(content: bytes) -> ArcticShiftPage:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Arctic Shift returned invalid JSON") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        error = payload.get("error") if isinstance(payload, dict) else None
        raise RuntimeError(f"Arctic Shift returned no data list: {error or 'unknown error'}")
    if not all(isinstance(item, dict) for item in data):
        raise RuntimeError("Arctic Shift returned a malformed data list")
    return ArcticShiftPage(content=content, data=tuple(data))


def _parse_post(
    item: Mapping[str, Any], *, ticker: str, expected_subreddit: str
) -> ArcticShiftPost:
    missing = [field for field in FIELDS if field not in item]
    if missing:
        raise RuntimeError("Arctic Shift post missing fields: " + ", ".join(missing))
    subreddit = str(item["subreddit"])
    if subreddit.casefold() != expected_subreddit.casefold():
        raise RuntimeError(
            f"Arctic Shift returned r/{subreddit} for r/{expected_subreddit} query"
        )
    try:
        created_at = datetime.fromtimestamp(float(item["created_utc"]), timezone.utc)
        score = int(item["score"] or 0)
        num_comments = int(item["num_comments"] or 0)
    except (TypeError, ValueError, OSError) as exc:
        raise RuntimeError("Arctic Shift post has invalid numeric metadata") from exc
    post_id = str(item["id"]).strip()
    if not post_id:
        raise RuntimeError("Arctic Shift post has an empty id")
    return ArcticShiftPost(
        post_id=post_id,
        ticker=ticker.upper(),
        subreddit=expected_subreddit,
        created_at=created_at,
        title=str(item["title"] or ""),
        selftext=str(item["selftext"] or ""),
        score=score,
        num_comments=num_comments,
    )


def _initial_slices(
    after: datetime, before: datetime
) -> list[tuple[datetime, datetime]]:
    slices = []
    cursor = after
    while cursor < before:
        slice_before = min(cursor + INITIAL_SLICE, before)
        slices.append((cursor, slice_before))
        if slice_before == before:
            break
        cursor = slice_before - timedelta(seconds=1)
    return slices


def _split_slice(
    after: datetime, before: datetime, subreddit: str
) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    duration = before - after
    if duration <= MINIMUM_SLICE:
        raise RuntimeError(
            f"Arctic Shift could not completely fetch r/{subreddit} "
            f"{_format_api_datetime(after)}..{_format_api_datetime(before)}"
        )
    midpoint = after + duration / 2
    overlap = timedelta(seconds=1)
    return (after, midpoint + overlap), (midpoint - overlap, before)


def _rate_limit_wait_seconds(headers: Message | Mapping[str, str] | None) -> float:
    retry_after = _header_float(headers, "Retry-After")
    if retry_after is not None:
        return max(retry_after, 1.0)
    reset = _header_float(headers, "X-RateLimit-Reset")
    if reset is None:
        return 61.0
    now = time.time()
    relative_reset = reset - now if reset > now else reset
    return max(relative_reset + 1.0, 1.0)


def _header_float(
    headers: Message | Mapping[str, str] | None, name: str
) -> float | None:
    if headers is None:
        return None
    try:
        value = headers.get(name)
        return float(value) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _next_raw_path(raw_dir: Path, ticker: str, subreddit: str) -> Path:
    sequence = 1
    while True:
        path = raw_dir / f"{ticker.upper()}-{subreddit}-{sequence:04d}.json"
        if not path.exists():
            return path
        sequence += 1


def _parse_bound(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_api_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def _trim_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 1:
        return value[:max_length]
    return value[:max_length] + "…"


if __name__ == "__main__":
    raise SystemExit(main())
