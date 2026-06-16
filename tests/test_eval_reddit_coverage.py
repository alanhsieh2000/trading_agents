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
