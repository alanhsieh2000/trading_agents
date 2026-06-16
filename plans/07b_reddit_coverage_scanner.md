# Plan B Reddit Coverage Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small Plan B scanner that ranks candidate backtest quarters by Reddit RSS coverage across tickers, subreddits, and rolling 7-day trading-date windows.

**Architecture:** Add a standalone evaluation module that fetches Reddit RSS search results, deduplicates posts, buckets them into candidate quarters, scores ticker-day coverage, and prints a compact recommendation. Keep it separate from the canonical dataset builder so it can guide Plan B selection without changing the main 2024-Q1 evaluation path.

**Tech Stack:** Python standard library (`argparse`, `datetime`, `time`, `urllib`, `xml.etree.ElementTree`, `dataclasses`), existing `trading_agents.config.get_settings`, existing Reddit user-agent/header conventions from `trading_agents.tools.sentiment`, `pytest`.

---

## File Structure

- Create `src/trading_agents/evaluation/reddit_coverage.py`: Reddit RSS probe client, parsing, deduplication, quarter/ticker-day scoring, CLI `main()`.
- Create `tests/test_eval_reddit_coverage.py`: unit tests for parsing, deduplication, scoring, ranking, and CLI output using mocked fetches only.
- Modify `pyproject.toml`: add `scan-reddit-coverage = "trading_agents.evaluation.reddit_coverage:main"` under `[project.scripts]`.
- Modify `plans/07_evaluation_backtest.md`: add a Plan B note explaining that candidate quarters are selected by ticker-day Reddit coverage, not raw post counts.

## Task 1: Data Model and RSS Parsing

**Files:**
- Create: `src/trading_agents/evaluation/reddit_coverage.py`
- Test: `tests/test_eval_reddit_coverage.py`

- [x] **Step 1: Write failing tests for Atom parsing and deduplication**

Create `tests/test_eval_reddit_coverage.py` with:

```python
from datetime import date, datetime, timezone

from trading_agents.evaluation.reddit_coverage import (
    RedditPost,
    dedupe_posts,
    parse_reddit_atom,
)


ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/</id>
    <title>AAPL thread</title>
    <published>2026-02-03T12:34:56+00:00</published>
    <link href="https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/" />
    <content type="html">&lt;div&gt;&lt;!-- SC_OFF --&gt;&lt;p&gt;Body &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;&lt;!-- SC_ON --&gt;&lt;/div&gt;</content>
  </entry>
  <entry>
    <id>https://www.reddit.com/r/stocks/comments/abc/aapl_thread/</id>
    <title>Duplicate AAPL thread</title>
    <published>2026-02-04T12:34:56+00:00</published>
    <link href="https://www.reddit.com/r/stocks/comments/abc/aapl_thread/" />
    <content type="html">Duplicate body</content>
  </entry>
</feed>"""


def test_parse_reddit_atom_extracts_posts():
    posts = parse_reddit_atom(ATOM, ticker="AAPL", subreddit="wallstreetbets")

    assert posts == [
        RedditPost(
            ticker="AAPL",
            subreddit="wallstreetbets",
            title="AAPL thread",
            published_at=datetime(2026, 2, 3, 12, 34, 56, tzinfo=timezone.utc),
            published_date=date(2026, 2, 3),
            url="https://www.reddit.com/r/wallstreetbets/comments/abc/aapl_thread/",
            body="Body text",
        ),
        RedditPost(
            ticker="AAPL",
            subreddit="wallstreetbets",
            title="Duplicate AAPL thread",
            published_at=datetime(2026, 2, 4, 12, 34, 56, tzinfo=timezone.utc),
            published_date=date(2026, 2, 4),
            url="https://www.reddit.com/r/stocks/comments/abc/aapl_thread/",
            body="Duplicate body",
        ),
    ]


def test_dedupe_posts_prefers_first_url():
    posts = parse_reddit_atom(ATOM, ticker="AAPL", subreddit="wallstreetbets")

    assert dedupe_posts(posts) == [posts[0]]
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py -q
```

Expected: import failure for missing `trading_agents.evaluation.reddit_coverage`.

- [x] **Step 3: Implement data model and parser**

Create `src/trading_agents/evaluation/reddit_coverage.py` with:

```python
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class RedditPost:
    ticker: str
    subreddit: str
    title: str
    published_at: datetime
    published_date: date
    url: str
    body: str


def parse_reddit_atom(payload: bytes, *, ticker: str, subreddit: str) -> list[RedditPost]:
    root = ET.fromstring(payload)
    posts: list[RedditPost] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        published_el = entry.find("atom:published", ATOM_NS)
        link_el = entry.find("atom:link", ATOM_NS)
        content_el = entry.find("atom:content", ATOM_NS)
        published_at = _parse_atom_datetime(
            published_el.text if published_el is not None else None
        )
        if published_at is None:
            continue
        posts.append(
            RedditPost(
                ticker=ticker.upper().strip(),
                subreddit=subreddit,
                title=_one_line(title_el.text if title_el is not None else ""),
                published_at=published_at,
                published_date=published_at.date(),
                url=link_el.attrib.get("href", "") if link_el is not None else "",
                body=_strip_reddit_html(
                    content_el.text if content_el is not None and content_el.text else ""
                ),
            )
        )
    return posts


def dedupe_posts(posts: list[RedditPost]) -> list[RedditPost]:
    seen: set[str] = set()
    deduped: list[RedditPost] = []
    for post in posts:
        key = _dedupe_key(post)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)
    return deduped


def _dedupe_key(post: RedditPost) -> str:
    match = re.search(r"/comments/([^/]+)/", post.url)
    if match:
        return match.group(1)
    return post.url or f"{post.published_at.isoformat()}:{post.title}"


def _parse_atom_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _strip_reddit_html(value: str) -> str:
    content = html.unescape(str(value or ""))
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->", 1)[1].split("<!-- SC_ON -->", 1)[0]
    return _one_line(re.sub(r"<[^>]+>", " ", content))


def _one_line(value: str) -> str:
    return " ".join(str(value).split())
```

- [x] **Step 4: Run parser tests to verify they pass**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py -q
```

Expected: `2 passed`.

- [x] **Step 5: Commit Task 1**

```bash
git add src/trading_agents/evaluation/reddit_coverage.py tests/test_eval_reddit_coverage.py
git commit -m "test: add reddit coverage parser"
```

## Task 2: Coverage Scoring

**Files:**
- Modify: `src/trading_agents/evaluation/reddit_coverage.py`
- Test: `tests/test_eval_reddit_coverage.py`

- [x] **Step 1: Write failing tests for quarter scoring and ranking**

Append to `tests/test_eval_reddit_coverage.py`:

```python
from trading_agents.evaluation.reddit_coverage import (
    CandidateQuarter,
    CoverageScore,
    score_candidate_quarters,
)


def _post(ticker: str, subreddit: str, yyyy_mm_dd: str) -> RedditPost:
    published_at = datetime.fromisoformat(yyyy_mm_dd + "T12:00:00+00:00")
    return RedditPost(
        ticker=ticker,
        subreddit=subreddit,
        title=f"{ticker} {yyyy_mm_dd}",
        published_at=published_at,
        published_date=published_at.date(),
        url=f"https://reddit.example/{ticker}/{subreddit}/{yyyy_mm_dd}",
        body="body",
    )


def test_score_candidate_quarters_uses_rolling_lookback_windows():
    candidates = [
        CandidateQuarter("2026-Q1", date(2026, 1, 1), date(2026, 1, 10)),
        CandidateQuarter("2026-Q2", date(2026, 4, 1), date(2026, 4, 10)),
    ]
    trading_days = {
        "2026-Q1": [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
        "2026-Q2": [date(2026, 4, 5), date(2026, 4, 6), date(2026, 4, 7)],
    }
    posts = [
        _post("AAPL", "wallstreetbets", "2026-01-02"),
        _post("GOOGL", "stocks", "2026-01-06"),
        _post("AMZN", "investing", "2026-01-07"),
        _post("AAPL", "wallstreetbets", "2026-04-01"),
        _post("AAPL", "stocks", "2026-04-04"),
        _post("GOOGL", "investing", "2026-04-02"),
        _post("AMZN", "stocks", "2026-04-03"),
        _post("AMZN", "investing", "2026-04-06"),
    ]

    scores = score_candidate_quarters(
        candidates,
        posts,
        tickers=("AAPL", "GOOGL", "AMZN"),
        subreddits=("wallstreetbets", "stocks", "investing"),
        trading_days_by_quarter=trading_days,
        lookback_days=7,
    )

    assert scores == [
        CoverageScore(
            quarter="2026-Q2",
            total_posts=5,
            ticker_day_count=9,
            covered_ticker_days_at_least_1=9,
            covered_ticker_days_at_least_3=0,
            min_ticker_coverage_at_least_1=1.0,
            nonzero_ticker_subreddit_pairs=5,
        ),
        CoverageScore(
            quarter="2026-Q1",
            total_posts=3,
            ticker_day_count=9,
            covered_ticker_days_at_least_1=6,
            covered_ticker_days_at_least_3=0,
            min_ticker_coverage_at_least_1=1 / 3,
            nonzero_ticker_subreddit_pairs=3,
        ),
    ]
```

- [x] **Step 2: Run scoring test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py::test_score_candidate_quarters_uses_rolling_lookback_windows -q
```

Expected: import failure for missing `CandidateQuarter`, `CoverageScore`, or `score_candidate_quarters`.

- [x] **Step 3: Implement scoring**

Add to `src/trading_agents/evaluation/reddit_coverage.py`:

```python
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import timedelta


@dataclass(frozen=True)
class CandidateQuarter:
    name: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class CoverageScore:
    quarter: str
    total_posts: int
    ticker_day_count: int
    covered_ticker_days_at_least_1: int
    covered_ticker_days_at_least_3: int
    min_ticker_coverage_at_least_1: float
    nonzero_ticker_subreddit_pairs: int


def score_candidate_quarters(
    candidates: Iterable[CandidateQuarter],
    posts: list[RedditPost],
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    trading_days_by_quarter: Mapping[str, list[date]],
    lookback_days: int,
) -> list[CoverageScore]:
    deduped = dedupe_posts(posts)
    scores = [
        _score_one_candidate(
            candidate,
            deduped,
            tickers=tickers,
            subreddits=subreddits,
            trading_days=trading_days_by_quarter[candidate.name],
            lookback_days=lookback_days,
        )
        for candidate in candidates
    ]
    return sorted(
        scores,
        key=lambda score: (
            score.covered_ticker_days_at_least_1 / max(score.ticker_day_count, 1),
            score.covered_ticker_days_at_least_3 / max(score.ticker_day_count, 1),
            score.min_ticker_coverage_at_least_1,
            score.total_posts,
        ),
        reverse=True,
    )


def _score_one_candidate(
    candidate: CandidateQuarter,
    posts: list[RedditPost],
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    trading_days: list[date],
    lookback_days: int,
) -> CoverageScore:
    quarter_posts = [
        post
        for post in posts
        if candidate.start_date <= post.published_date <= candidate.end_date
        and post.ticker in tickers
        and post.subreddit in subreddits
    ]
    posts_by_ticker: dict[str, list[RedditPost]] = defaultdict(list)
    pairs: set[tuple[str, str]] = set()
    for post in quarter_posts:
        posts_by_ticker[post.ticker].append(post)
        pairs.add((post.ticker, post.subreddit))

    covered_1 = 0
    covered_3 = 0
    ticker_covered_counts: dict[str, int] = {ticker: 0 for ticker in tickers}
    for ticker in tickers:
        for trade_date in trading_days:
            start = trade_date - timedelta(days=lookback_days)
            count = sum(
                1
                for post in posts_by_ticker.get(ticker, [])
                if start <= post.published_date <= trade_date
            )
            if count >= 1:
                covered_1 += 1
                ticker_covered_counts[ticker] += 1
            if count >= 3:
                covered_3 += 1

    trading_day_count = len(trading_days)
    min_ticker_coverage = min(
        (
            ticker_covered_counts[ticker] / trading_day_count
            for ticker in tickers
        ),
        default=0.0,
    )
    return CoverageScore(
        quarter=candidate.name,
        total_posts=len(quarter_posts),
        ticker_day_count=len(tickers) * trading_day_count,
        covered_ticker_days_at_least_1=covered_1,
        covered_ticker_days_at_least_3=covered_3,
        min_ticker_coverage_at_least_1=min_ticker_coverage,
        nonzero_ticker_subreddit_pairs=len(pairs),
    )
```

Also move the original `from datetime import date, datetime, timezone` import to include `timedelta`, and combine duplicate imports cleanly.

- [x] **Step 4: Run scoring tests**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py -q
```

Expected: all tests in `test_eval_reddit_coverage.py` pass.

- [x] **Step 5: Commit Task 2**

```bash
git add src/trading_agents/evaluation/reddit_coverage.py tests/test_eval_reddit_coverage.py
git commit -m "feat: score reddit coverage by ticker-day"
```

## Task 3: RSS Probe Client and CLI

**Files:**
- Modify: `src/trading_agents/evaluation/reddit_coverage.py`
- Modify: `pyproject.toml`
- Test: `tests/test_eval_reddit_coverage.py`

- [ ] **Step 1: Write failing CLI test**

Append to `tests/test_eval_reddit_coverage.py`:

```python
from trading_agents.evaluation import reddit_coverage


def test_main_prints_ranked_recommendation(monkeypatch, capsys):
    def fake_fetch_all_posts(*, tickers, subreddits, queries, request_delay_seconds):
        assert tickers == ("AAPL", "GOOGL", "AMZN")
        assert subreddits == ("wallstreetbets", "stocks", "investing")
        assert queries["AAPL"] == ("AAPL", "$AAPL", "Apple")
        assert request_delay_seconds == 3.0
        return [
            _post("AAPL", "wallstreetbets", "2026-01-02"),
            _post("GOOGL", "stocks", "2026-01-03"),
            _post("AMZN", "investing", "2026-01-04"),
            _post("AAPL", "wallstreetbets", "2025-10-02"),
        ]

    def fake_trading_days(start_date, end_date, benchmark):
        if start_date == date(2026, 1, 1):
            return [date(2026, 1, 5), date(2026, 1, 6)]
        return [start_date]

    monkeypatch.setattr(reddit_coverage, "fetch_all_posts", fake_fetch_all_posts)
    monkeypatch.setattr(reddit_coverage, "fetch_trading_days", fake_trading_days)

    reddit_coverage.main([])

    output = capsys.readouterr().out
    assert "Plan B Reddit coverage scan" in output
    assert "1. 2026-Q1" in output
    assert "Recommended Plan B period: 2026-Q1" in output
```

- [ ] **Step 2: Run CLI test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py::test_main_prints_ranked_recommendation -q
```

Expected: failure for missing `fetch_all_posts`, `fetch_trading_days`, or `main`.

- [ ] **Step 3: Implement RSS client and CLI**

Add to `src/trading_agents/evaluation/reddit_coverage.py`:

```python
import argparse
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from trading_agents.config import get_settings
from trading_agents.tools.sentiment import REDDIT_HEADERS


DEFAULT_CANDIDATES = (
    CandidateQuarter("2025-Q3", date(2025, 7, 1), date(2025, 9, 30)),
    CandidateQuarter("2025-Q4", date(2025, 10, 1), date(2025, 12, 31)),
    CandidateQuarter("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
)
DEFAULT_QUERY_ALIASES = {
    "AAPL": ("AAPL", "$AAPL", "Apple"),
    "GOOGL": ("GOOGL", "$GOOGL", "Google"),
    "AMZN": ("AMZN", "$AMZN", "Amazon"),
}


def fetch_all_posts(
    *,
    tickers: tuple[str, ...],
    subreddits: tuple[str, ...],
    queries: Mapping[str, tuple[str, ...]],
    request_delay_seconds: float,
) -> list[RedditPost]:
    posts: list[RedditPost] = []
    for ticker in tickers:
        for subreddit in subreddits:
            for query in queries.get(ticker, (ticker,)):
                posts.extend(fetch_rss_posts(ticker=ticker, subreddit=subreddit, query=query))
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)
    return dedupe_posts(posts)


def fetch_rss_posts(*, ticker: str, subreddit: str, query: str) -> list[RedditPost]:
    qs = urlencode(
        {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "t": "year",
            "limit": 100,
        }
    )
    url = f"https://www.reddit.com/r/{quote(subreddit)}/search.rss?{qs}"
    request = Request(url, headers=REDDIT_HEADERS)
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
    except HTTPError as exc:
        print(f"warning: Reddit RSS {ticker} r/{subreddit} query={query!r} HTTP {exc.code}")
        return []
    except (URLError, TimeoutError) as exc:
        print(f"warning: Reddit RSS {ticker} r/{subreddit} query={query!r} failed: {exc}")
        return []
    return parse_reddit_atom(payload, ticker=ticker, subreddit=subreddit)


def fetch_trading_days(start_date: date, end_date: date, benchmark: str) -> list[date]:
    frame = yf.download(
        benchmark,
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=False,
    )
    if frame.empty:
        return []
    return [idx.date() for idx in frame.index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Reddit RSS coverage for Plan B backtest quarters.")
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--lookback-days", type=int, default=7)
    args = parser.parse_args(argv)

    settings = get_settings()
    tickers = tuple(settings.evaluation.tickers)
    subreddits = tuple(settings.sentiment.reddit_subreddits)
    queries = {
        ticker: DEFAULT_QUERY_ALIASES.get(ticker, (ticker,))
        for ticker in tickers
    }
    posts = fetch_all_posts(
        tickers=tickers,
        subreddits=subreddits,
        queries=queries,
        request_delay_seconds=args.delay,
    )
    trading_days = {
        candidate.name: fetch_trading_days(
            candidate.start_date,
            candidate.end_date,
            settings.evaluation.benchmark,
        )
        for candidate in DEFAULT_CANDIDATES
    }
    scores = score_candidate_quarters(
        DEFAULT_CANDIDATES,
        posts,
        tickers=tickers,
        subreddits=subreddits,
        trading_days_by_quarter=trading_days,
        lookback_days=args.lookback_days,
    )
    print("Plan B Reddit coverage scan")
    pair_count = len(tickers) * len(subreddits)
    for index, score in enumerate(scores, start=1):
        pct1 = 100 * score.covered_ticker_days_at_least_1 / max(score.ticker_day_count, 1)
        pct3 = 100 * score.covered_ticker_days_at_least_3 / max(score.ticker_day_count, 1)
        print(
            f"{index}. {score.quarter}: posts={score.total_posts}, "
            f">=1 coverage={pct1:.1f}%, >=3 coverage={pct3:.1f}%, "
            f"min ticker coverage={100 * score.min_ticker_coverage_at_least_1:.1f}%, "
            f"pairs={score.nonzero_ticker_subreddit_pairs}/{pair_count}"
        )
    if scores:
        print(f"Recommended Plan B period: {scores[0].quarter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register console script**

In `pyproject.toml`, add under `[project.scripts]`:

```toml
scan-reddit-coverage = "trading_agents.evaluation.reddit_coverage:main"
```

Keep any existing scripts unchanged.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
uv run pytest tests/test_eval_reddit_coverage.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/trading_agents/evaluation/reddit_coverage.py tests/test_eval_reddit_coverage.py pyproject.toml
git commit -m "feat: add reddit coverage scanner cli"
```

## Task 4: Documentation and Plan 07 Update

**Files:**
- Modify: `plans/07_evaluation_backtest.md`
- Test: none

- [ ] **Step 1: Add Plan B selection note to Plan 07**

In `plans/07_evaluation_backtest.md`, add this to **Decision Log**:

```markdown
- Decision: Select any Plan B backtest quarter by Reddit ticker-day coverage, not by
  raw Reddit post count.
  Rationale: A quarter with many posts for one ticker is not useful if the other
  evaluation tickers have sparse sentiment evidence. The Plan B scanner ranks
  2025-Q3, 2025-Q4, and 2026-Q1 by the share of ticker trading days whose 7-day
  lookback window has at least one Reddit post, then by stricter >=3-post coverage,
  minimum per-ticker coverage, and total posts.
  Date/Author: 2026-06-15 / Codex
```

Add this to **Plan of Work** near the `--scan-periods` builder discussion:

```markdown
Before changing the configured backtest dates for Plan B, run
`uv run scan-reddit-coverage`. Treat its recommended quarter as the candidate
Plan B period only if every ticker has nonzero coverage and the coverage table is
recorded in this plan. If Reddit coverage is concentrated in a single ticker,
prefer a no-Reddit ablation or continue waiting for Exa historical Reddit access
instead of pretending the quarter is equivalent to the canonical evaluation.
```

- [ ] **Step 2: Run markdown smoke check**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
text = Path("plans/07_evaluation_backtest.md").read_text()
assert "Select any Plan B backtest quarter by Reddit ticker-day coverage" in text
assert "uv run scan-reddit-coverage" in text
print("plan 07 note ok")
PY
```

Expected: `plan 07 note ok`.

- [ ] **Step 3: Commit Task 4**

```bash
git add plans/07_evaluation_backtest.md
git commit -m "docs: record plan b reddit coverage selection"
```

## Task 5: Final Verification

**Files:**
- No code changes unless verification exposes a bug.

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest tests/test_eval_reddit_coverage.py tests/test_trading_tools.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run live scanner smoke**

```bash
uv run scan-reddit-coverage --delay 3
```

Expected: command prints `Plan B Reddit coverage scan`, three ranked quarters, and `Recommended Plan B period: ...`. If Reddit returns `HTTP 429`, rerun once with `--delay 10` and record the warning in `plans/07_evaluation_backtest.md`.

- [ ] **Step 4: Record live scanner result in Plan 07**

Add a dated **Surprises & Discoveries** entry with:

```markdown
- Observation: The Plan B Reddit coverage scanner ranked the candidate quarters as
  follows: [paste exact command output summary].
  Evidence: `uv run scan-reddit-coverage --delay 3` on 2026-06-15 printed [summary].
```

- [ ] **Step 5: Commit verification note**

```bash
git add plans/07_evaluation_backtest.md
git commit -m "docs: record reddit coverage scan result"
```

## Assumptions and Defaults

- Candidate quarters are exactly `2025-Q3`, `2025-Q4`, and `2026-Q1`.
- Tickers come from `get_settings().evaluation.tickers`, currently `AAPL`, `GOOGL`, `AMZN`.
- Subreddits come from `get_settings().sentiment.reddit_subreddits`, currently `wallstreetbets`, `stocks`, `investing`.
- Query aliases are hard-coded only for the three evaluation tickers: `AAPL/$AAPL/Apple`, `GOOGL/$GOOGL/Google`, `AMZN/$AMZN/Amazon`.
- Reddit RSS probes use `sort=new&t=year&limit=100`; `sort=old` is not used because probes showed it is not reliable as chronological ordering.
- One RSS request returns at most 100 entries and no pagination link is assumed.
- The scanner recommends a quarter; it does not change `EvaluationSettings.start_date` or `end_date`.
