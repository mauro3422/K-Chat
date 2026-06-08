from ddgs import DDGS

DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    }
}

def run(query: str, max_results: int = 3, _retries: int = 2, **kwargs) -> str:
    import time
    last_error = None
    for attempt in range(_retries + 1):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "No se encontraron resultados."
            return "\n".join(
                f"{r['title']}: {r['body']} ({r['href']})" for r in results
            )
        except Exception as e:
            last_error = e
            if attempt < _retries:
                time.sleep(1.5 * (attempt + 1))
    return f"Error al buscar (tras {_retries + 1} intentos): {last_error}"
