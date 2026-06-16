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
