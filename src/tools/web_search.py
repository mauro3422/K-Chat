import logging
import os
from typing import Any
import httpx

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
SEARCH_TIMEOUT = 15.0


def _searxng_url() -> str:
    return os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080")

# Module-level constant, never mutated after init — thread-safe
DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web. Always use this when the user asks about current events, recent info, or anything that might have changed since your training data. Supports categories, language, time range, and pagination.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 3, max: 20)",
                    "default": 3
                },
                "categories": {
                    "type": "string",
                    "description": "Comma-separated categories. Available: general, news, images, videos, music, files, social, science, it, web, wikimedia, dictionaries, maps, apps",
                    "default": "general"
                },
                "language": {
                    "type": "string",
                    "description": "Language code to filter results (e.g. 'es', 'en', 'fr'). Leave empty for automatic detection.",
                    "default": ""
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range for results: 'day', 'week', 'month', or 'year'. Empty for no filter.",
                    "enum": ["", "day", "week", "month", "year"],
                    "default": ""
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination (starts at 1)",
                    "default": 1
                },
                "safe_search": {
                    "type": "integer",
                    "description": "Safe search level: 0=None, 1=Moderate, 2=Strict",
                    "enum": [0, 1, 2],
                    "default": 0
                }
            },
            "required": ["query"]
        }
    }
}


def _format_result(r: dict[str, Any]) -> str:
    title = r.get("title", "")
    content = r.get("content", "")
    url = r.get("url", "")
    engine = r.get("engine", "")
    published = r.get("publishedDate", "")
    parts = [f"{title}: {content} ({url})"]
    if engine:
        parts.append(f"  [source: {engine}]")
    if published:
        parts.append(f"  [published: {published}]")
    return "\n".join(parts)


VALID_TIME_RANGES = frozenset({"", "day", "week", "month", "year"})


def _search_with_retry(
    query: str,
    results_lang: str,
    timeout: float,
    _retries: int,
    *,
    categories: str = "general",
    page: int = 1,
    safe_search: int = 0,
    time_range: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "categories": categories or "general",
        "pageno": page,
        "safesearch": safe_search,
    }
    if results_lang:
        params["language"] = results_lang
    if time_range:
        params["time_range"] = time_range

    for attempt in range(_retries + 1):
        try:
            resp = httpx.get(f"{_searxng_url()}/search", params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json(), None
        except Exception:
            logger.exception("Search attempt %d/%d failed", attempt + 1, _retries + 1)
            if attempt < _retries:
                import time
                time.sleep(1.5 * (attempt + 1))
            else:
                return None, f"Search error (after {_retries + 1} attempts)."
    return None, "Search error (unreachable)"


def _search_and_format_results(
    query: str,
    max_results: int,
    categories: str,
    language: str,
    time_range: str,
    page: int,
    safe_search: int,
    _retries: int,
) -> str:
    data, error = _search_with_retry(
        query, language, 15.0, _retries,
        categories=categories, page=page, safe_search=safe_search, time_range=time_range,
    )
    if error or data is None:
        return error or "Search failed."

    results = data.get("results", [])[:max_results]

    if not results:
        return "No results found."

    out = [f"Search results for: {query}"]
    if categories and categories != "general":
        out[0] += f" (categories: {categories})"
    out.append("")
    for i, r in enumerate(results, 1):
        out.append(f"{i}. {_format_result(r)}")
        out.append("")

    suggestions = data.get("suggestions", [])
    if suggestions:
        out.append(f"Suggestions: {', '.join(suggestions[:5])}")
        out.append("")

    infoboxes = data.get("infoboxes", [])
    if infoboxes:
        for ib in infoboxes:
            ib_content = ib.get("content", "")
            ib_url = ib.get("urls", [{}])[0].get("url", "") if ib.get("urls") else ""
            if ib_content:
                out.append(f"Infobox: {ib_content}")
                if ib_url:
                    out.append(f"  {ib_url}")
                out.append("")

    return "\n".join(out).strip()


def run(
    query: str,
    max_results: int = 3,
    categories: str = "general",
    language: str = "",
    time_range: str = "",
    page: int = 1,
    safe_search: int = 0,
    _retries: int = 2,
    **kwargs: Any
) -> str:
    query = (query or "").strip()
    if not query:
        return "[ERROR] The search query is empty. Provide text to search for."

    max_results = min(max(max_results, 1), 20)

    if time_range and time_range not in VALID_TIME_RANGES:
        return f"[ERROR] '{time_range}' is not a valid time_range. Use: day, week, month, or year."

    if page < 1:
        return f"[ERROR] page={page} is not valid. Page must be 1 or greater."
    page = max(page, 1)

    result = _search_and_format_results(
        query, max_results, categories, language, time_range, page, safe_search, _retries,
    )
    return result
