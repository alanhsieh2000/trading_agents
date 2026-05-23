import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def fetch_stocktwits_messages(ticker: str, limit: int = 10) -> str:
    symbol = ticker.upper().strip()
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{quote(symbol)}.json?limit={limit}"
    try:
        payload = _fetch_json(url)
    except Exception:
        return f"No data available for StockTwits messages for {symbol}."

    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not messages:
        return f"No data available for StockTwits messages for {symbol}."

    lines = [f"StockTwits messages for {symbol}:"]
    for message in messages[: max(limit, 0)]:
        user = (message.get("user") or {}).get("username", "unknown")
        created_at = message.get("created_at", "unknown date")
        body = _one_line(message.get("body", ""))
        lines.append(f"- {created_at} {user}: {body}")
    return "\n".join(lines)


def fetch_reddit_posts(query: str, limit: int = 10) -> str:
    clean_query = query.strip()
    encoded_query = quote(clean_query)
    url = (
        "https://www.reddit.com/search.json"
        f"?q={encoded_query}&sort=new&limit={max(limit, 0)}"
    )
    headers = {"User-Agent": "trading-agents/0.1"}
    try:
        payload = _fetch_json(url, headers=headers)
    except Exception:
        return f"No data available for Reddit posts for {clean_query}."

    children = ((payload.get("data") or {}).get("children") or []) if isinstance(payload, dict) else []
    if not children:
        return f"No data available for Reddit posts for {clean_query}."

    lines = [f"Reddit posts for {clean_query}:"]
    for child in children[: max(limit, 0)]:
        data = child.get("data") or {}
        subreddit = data.get("subreddit_name_prefixed") or data.get("subreddit") or "unknown subreddit"
        title = _one_line(data.get("title", "Untitled post"))
        permalink = data.get("permalink")
        url_text = f"https://www.reddit.com{permalink}" if permalink else "No URL available"
        lines.append(f"- {subreddit}: {title} - {url_text}")
    return "\n".join(lines)


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not fetch JSON from {url}") from exc


def _one_line(value: str) -> str:
    return " ".join(str(value).split())
