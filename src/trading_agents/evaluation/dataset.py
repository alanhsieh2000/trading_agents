"""DuckDB-backed prepared dataset for the evaluation backtest.

The dataset holds two tables:

- ``tool_outputs(tool_name, ticker, as_of_date, payload)`` — the exact text
  block each analyst tool returns, keyed by the run's ``trade_date``
  (``as_of_date``). In evaluation mode the analyst tools and the analyst
  stage's pre-fetched sentiment blocks read these recorded payloads instead of
  calling live APIs.
- ``prices(symbol, date, close)`` — daily close prices for the evaluated
  tickers and the benchmark across the buffered range, used by the exchange
  simulator and by the portfolio stage's realized-return fetcher.
- ``reddit_posts(ticker, subreddit, url, ...)`` — raw Reddit posts collected
  from Plan B RSS or loaded from the canonical Arctic Shift archive, kept
  separately from replay payloads so reruns can audit the source material.

Both tables use a primary key so the builder can upsert idempotently with
``INSERT OR REPLACE``: rerunning the builder refreshes rows rather than
duplicating them.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import duckdb

from trading_agents.config import get_settings


class EvalDataset:
    """Read/write access to the prepared evaluation dataset.

    ``path`` defaults to ``settings.evaluation.dataset_path``. The connection is
    held open for the lifetime of the instance; call :meth:`close` (or use the
    instance as a context manager) to release it.
    """

    def __init__(self, path: str | Path | None = None, *, read_only: bool = False) -> None:
        if path is None:
            path = get_settings().evaluation.dataset_path
        self.path = Path(path)
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.exists():
            raise FileNotFoundError(f"Evaluation dataset not found: {self.path}")
        self._conn = duckdb.connect(str(self.path), read_only=read_only)
        if not read_only:
            self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_outputs (
                tool_name  TEXT NOT NULL,
                ticker     TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                payload    TEXT NOT NULL,
                PRIMARY KEY (tool_name, ticker, as_of_date)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prices (
                symbol TEXT   NOT NULL,
                date   TEXT   NOT NULL,
                close  DOUBLE NOT NULL,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reddit_posts (
                ticker         TEXT NOT NULL,
                subreddit      TEXT NOT NULL,
                published_at   TEXT NOT NULL,
                published_date TEXT NOT NULL,
                url            TEXT NOT NULL,
                title          TEXT NOT NULL,
                body           TEXT NOT NULL,
                source_post_id TEXT,
                score          INTEGER,
                num_comments   INTEGER,
                PRIMARY KEY (ticker, subreddit, url)
            )
            """
        )
        self._conn.execute(
            "ALTER TABLE reddit_posts ADD COLUMN IF NOT EXISTS source_post_id TEXT"
        )
        self._conn.execute(
            "ALTER TABLE reddit_posts ADD COLUMN IF NOT EXISTS score INTEGER"
        )
        self._conn.execute(
            "ALTER TABLE reddit_posts ADD COLUMN IF NOT EXISTS num_comments INTEGER"
        )

    # -- writes ---------------------------------------------------------------

    def put_tool_output(
        self, tool_name: str, ticker: str, as_of_date: str, payload: str
    ) -> None:
        """Upsert one recorded tool output."""
        self._conn.execute(
            "INSERT OR REPLACE INTO tool_outputs "
            "(tool_name, ticker, as_of_date, payload) VALUES (?, ?, ?, ?)",
            [tool_name, ticker.upper(), as_of_date, payload],
        )

    def put_tool_outputs(
        self, rows: list[tuple[str, str, str, str]]
    ) -> None:
        """Atomically upsert tool-output rows.

        Rows are ``(tool_name, ticker, as_of_date, payload)``. Rendering callers
        can prepare and validate a complete replacement set before any stored
        payload changes.
        """
        if not rows:
            return
        self._conn.execute("BEGIN TRANSACTION")
        try:
            self._conn.executemany(
                "INSERT OR REPLACE INTO tool_outputs "
                "(tool_name, ticker, as_of_date, payload) VALUES (?, ?, ?, ?)",
                [
                    (tool_name, ticker.upper(), as_of_date, payload)
                    for tool_name, ticker, as_of_date, payload in rows
                ],
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def put_prices(self, symbol: str, rows: list[tuple[str, float]]) -> None:
        """Upsert a symbol's ``(date, close)`` rows."""
        if not rows:
            return
        self._conn.executemany(
            "INSERT OR REPLACE INTO prices (symbol, date, close) VALUES (?, ?, ?)",
            [(symbol.upper(), date, float(close)) for date, close in rows],
        )

    def put_reddit_posts(
        self,
        rows: list[
            tuple[
                str,
                str,
                str,
                str,
                str,
                str,
                str,
                str | None,
                int | None,
                int | None,
            ]
        ],
    ) -> None:
        """Upsert raw Reddit posts.

        Rows are ``(ticker, subreddit, published_at, published_date, url, title,
        body, source_post_id, score, num_comments)``. The primary key
        intentionally includes ``ticker`` because one post can be relevant to
        more than one ticker query.
        """
        if not rows:
            return
        self._conn.executemany(
            "INSERT OR REPLACE INTO reddit_posts "
            "(ticker, subreddit, published_at, published_date, url, title, body, "
            "source_post_id, score, num_comments) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    ticker.upper(),
                    subreddit,
                    published_at,
                    published_date,
                    url,
                    title,
                    body,
                    source_post_id,
                    score,
                    num_comments,
                )
                for (
                    ticker,
                    subreddit,
                    published_at,
                    published_date,
                    url,
                    title,
                    body,
                    source_post_id,
                    score,
                    num_comments,
                ) in rows
            ],
        )

    def matching_tool_output_dates(
        self, tool_name: str, ticker: str, payload: str
    ) -> list[str]:
        """Return dates whose recorded output exactly matches ``payload``."""
        rows = self._conn.execute(
            "SELECT as_of_date FROM tool_outputs "
            "WHERE tool_name = ? AND ticker = ? AND payload = ? ORDER BY as_of_date",
            [tool_name, ticker.upper(), payload],
        ).fetchall()
        return [str(as_of_date) for (as_of_date,) in rows]

    def replace_matching_tool_outputs(
        self,
        tool_name: str,
        ticker: str,
        replacements: Mapping[str, str],
        *,
        expected_payload: str,
    ) -> int:
        """Atomically replace guarded tool outputs and reject stale targets."""
        symbol = ticker.upper()
        dates = sorted(replacements)
        if not dates:
            return 0

        self._conn.execute("BEGIN TRANSACTION")
        try:
            rows = self._conn.execute(
                "SELECT as_of_date FROM tool_outputs "
                "WHERE tool_name = ? AND ticker = ? AND payload = ? "
                "AND as_of_date IN (SELECT UNNEST(?)) ORDER BY as_of_date",
                [tool_name, symbol, expected_payload, dates],
            ).fetchall()
            guarded_dates = [str(as_of_date) for (as_of_date,) in rows]
            if guarded_dates != dates:
                raise RuntimeError(
                    "Tool outputs changed before patch commit; no rows were updated"
                )
            self._conn.executemany(
                "UPDATE tool_outputs SET payload = ? "
                "WHERE tool_name = ? AND ticker = ? AND as_of_date = ? "
                "AND payload = ?",
                [
                    (
                        replacements[as_of_date],
                        tool_name,
                        symbol,
                        as_of_date,
                        expected_payload,
                    )
                    for as_of_date in dates
                ],
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return len(dates)

    # -- reads ----------------------------------------------------------------

    def tool_output(self, tool_name: str, ticker: str, as_of_date: str) -> str:
        """Return the recorded payload, or raise if the row is missing.

        Evaluation runs must fail loudly on a gap rather than silently feeding
        empty data into an analyst task.
        """
        row = self._conn.execute(
            "SELECT payload FROM tool_outputs "
            "WHERE tool_name = ? AND ticker = ? AND as_of_date = ?",
            [tool_name, ticker.upper(), as_of_date],
        ).fetchone()
        if row is None:
            raise KeyError(
                f"No recorded output for tool={tool_name!r} ticker={ticker!r} "
                f"as_of_date={as_of_date!r} in {self.path}. Rebuild the dataset "
                "with `uv run build-eval-dataset`."
            )
        return str(row[0])

    def close_series(self, symbol: str) -> list[tuple[str, float]]:
        """Return a symbol's ``(date, close)`` series sorted ascending by date."""
        rows = self._conn.execute(
            "SELECT date, close FROM prices WHERE symbol = ? ORDER BY date",
            [symbol.upper()],
        ).fetchall()
        return [(str(date), float(close)) for date, close in rows]

    def reddit_post_rows(
        self, ticker: str | None = None
    ) -> list[dict[str, str | None]]:
        """Return raw Reddit post rows sorted by ticker/date/subreddit."""
        if ticker is None:
            rows = self._conn.execute(
                "SELECT ticker, subreddit, published_at, published_date, url, title, body, "
                "source_post_id, score, num_comments "
                "FROM reddit_posts ORDER BY ticker, published_at, subreddit, url"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT ticker, subreddit, published_at, published_date, url, title, body, "
                "source_post_id, score, num_comments "
                "FROM reddit_posts WHERE ticker = ? "
                "ORDER BY ticker, published_at, subreddit, url",
                [ticker.upper()],
            ).fetchall()
        keys = (
            "ticker",
            "subreddit",
            "published_at",
            "published_date",
            "url",
            "title",
            "body",
            "source_post_id",
            "score",
            "num_comments",
        )
        return [
            dict(
                zip(
                    keys,
                    (None if value is None else str(value) for value in row),
                    strict=True,
                )
            )
            for row in rows
        ]

    def transaction_days(
        self,
        *,
        benchmark: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        """Return benchmark trading days within the backtest window, ascending.

        Defaults pull the benchmark symbol and window bounds from
        ``settings.evaluation``; pass overrides for tests.
        """
        evaluation = get_settings().evaluation
        benchmark = benchmark or evaluation.benchmark
        start_date = start_date or evaluation.start_date
        end_date = end_date or evaluation.end_date
        rows = self._conn.execute(
            "SELECT date FROM prices WHERE symbol = ? AND date >= ? AND date <= ? "
            "ORDER BY date",
            [benchmark.upper(), start_date, end_date],
        ).fetchall()
        return [str(date) for (date,) in rows]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EvalDataset:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
