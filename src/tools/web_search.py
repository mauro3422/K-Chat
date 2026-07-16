import logging
from typing import Any
import httpx
from src.utils.async_utils import sleep

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
SEARCH_TIMEOUT = 15.0


def _searxng_url(config=None) -> str:
    if config is None:
        from src.config_loader import load_config
        config = load_config()
    return config.searxng_url

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


def _empty_results_message(fallback_used: bool) -> str:
    if fallback_used:
        return "No results found. SearXNG returned 0 results after Bing fallback."
    return "No results found. SearXNG returned 0 results."


async def _search_with_retry(
    query: str,
    results_lang: str,
    timeout: float,
    _retries: int,
    *,
    config=None,
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

    async with httpx.AsyncClient() as client:
        for attempt in range(_retries + 1):
            try:
                resp = await client.get(f"{_searxng_url(config=config)}/search", params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json(), None
            except Exception:
                logger.exception("Search attempt %d/%d failed", attempt + 1, _retries + 1)
                if attempt < _retries:
                    await sleep(1.5 * (attempt + 1))
                else:
                    return None, f"Search error (after {_retries + 1} attempts)."
    return None, "Search error (unreachable)"


async def _search_with_engines(
    query: str,
    language: str,
    time_range: str,
    page: int,
    safe_search: int,
    engines: str | None,
    config=None,
) -> dict | None:
    """Hit SearXNG with an optional explicit engine list.

    ``engines`` is a comma-separated engine list (e.g. ``"bing"``) or
    ``None`` to use the instance's default engine selection.
    """
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "pageno": page,
        "safesearch": safe_search,
    }
    if engines:
        params["engines"] = engines
    if language:
        params["language"] = language
    if time_range:
        params["time_range"] = time_range
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_searxng_url(config=config)}/search",
                params=params,
                timeout=SEARCH_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("Search with engines=%s failed", engines or "default")
        return None


async def _search_and_format_results(
    query: str,
    max_results: int,
    categories: str,
    language: str,
    time_range: str,
    page: int,
    safe_search: int,
    _retries: int,
    config=None,
) -> str:
    data, error = await _search_with_retry(
        query, language, SEARCH_TIMEOUT, _retries,
        config=config, categories=categories, page=page, safe_search=safe_search, time_range=time_range,
    )
    if error or data is None:
        return error or "Search failed."

    results = data.get("results", [])[:max_results]
    source_data = data
    bing_fallback_used = False

    # Default engines (DuckDuckGo, Google) often rate-limit automated
    # queries.  Fall back to Bing which is more permissive with
    # self-hosted SearXNG instances.
    bing_data: dict[str, Any] | None = None
    if not results:
        logger.info("No results from default engines — retrying with Bing")
        bing_data = await _search_with_engines(
            query, language, time_range, page, safe_search, "bing", config=config,
        )
        if bing_data:
            bing_results = bing_data.get("results", [])[:max_results]
            if bing_results:
                results = bing_results
                source_data = bing_data
                bing_fallback_used = True

    if not results:
        if bing_data is None:
            return "No results found. SearXNG returned 0 results and Bing fallback failed."
        return _empty_results_message(fallback_used=True)

    out = [f"Search results for: {query}"]
    if categories and categories != "general":
        out[0] += f" (categories: {categories})"
    if bing_fallback_used:
        out.append("Fallback engine: bing")
    out.append("")
    for i, r in enumerate(results, 1):
        out.append(f"{i}. {_format_result(r)}")
        out.append("")

    suggestions = source_data.get("suggestions", [])
    if suggestions:
        out.append(f"Suggestions: {', '.join(suggestions[:5])}")
        out.append("")

    infoboxes = source_data.get("infoboxes", [])
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


async def run(config=None, **kwargs: Any) -> str:
    query = kwargs.get("query") or kwargs.get("q") or kwargs.get("search_query", "")
    max_results = int(kwargs.get("max_results", kwargs.get("max", kwargs.get("limit", 3))))
    categories = kwargs.get("categories") or kwargs.get("category", "general")
    language = kwargs.get("language") or kwargs.get("lang") or kwargs.get("locale", "")
    time_range = kwargs.get("time_range") or kwargs.get("time") or kwargs.get("timerange", "")
    page = int(kwargs.get("page", kwargs.get("page_num", kwargs.get("pageno", 1))))
    safe_search = int(kwargs.get("safe_search", kwargs.get("safe", kwargs.get("safesearch", 0))))
    _retries = int(kwargs.get("_retries", 2))

    query = (query or "").strip()
    if not query:
        return "[ERROR] The search query is empty. Provide text to search for."

    max_results = min(max(max_results, 1), 20)

    if time_range and time_range not in VALID_TIME_RANGES:
        return f"[ERROR] '{time_range}' is not a valid time_range. Use: day, week, month, or year."

    if page < 1:
        return f"[ERROR] page={page} is not valid. Page must be 1 or greater."
    page = max(page, 1)

    result = await _search_and_format_results(
        query, max_results, categories, language, time_range, page, safe_search, _retries, config=config,
    )
    return result
