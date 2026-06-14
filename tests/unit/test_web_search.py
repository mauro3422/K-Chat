import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock


from src.tools.web_search import run, DEFINITION


@pytest.mark.anyio
async def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "web_search"
    props = DEFINITION["function"]["parameters"]["properties"]
    assert "query" in props
    assert "max_results" in props
    assert "categories" in props
    assert "language" in props
    assert "time_range" in props
    assert "page" in props
    assert "safe_search" in props
    assert DEFINITION["function"]["parameters"]["required"] == ["query"]


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_default_params(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "T1", "content": "C1", "url": "https://example.com/1", "engine": "google"},
        ]
    }
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="test")
    assert "T1" in result
    assert "C1" in result

    called_params = mock_client.get.call_args[1]["params"]
    assert called_params["q"] == "test"
    assert called_params["categories"] == "general"
    assert called_params["format"] == "json"


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_with_all_params(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"title": "T1", "content": "C1", "url": "https://ex.com/1"}]}
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    await run(query="test", max_results=5, categories="news,it", language="es", time_range="week", page=2, safe_search=1)

    called_params = mock_client.get.call_args[1]["params"]
    assert called_params["q"] == "test"
    assert called_params["categories"] == "news,it"
    assert called_params["language"] == "es"
    assert called_params["time_range"] == "week"
    assert called_params["pageno"] == 2
    assert called_params["safesearch"] == 1


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_ignores_extra_kwargs(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"title": "T1", "content": "C1", "url": "https://ex.com/1"}]}
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="test", _session_id="x", foo="bar")
    assert "T1" in result


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_empty_results(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="nothing")
    assert "No results found" in result


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_with_suggestions(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"title": "T1", "content": "C1", "url": "https://ex.com/1"}],
        "suggestions": ["sug1", "sug2"],
    }
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="test")
    assert "sug1" in result


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_with_infobox(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"title": "T1", "content": "C1", "url": "https://ex.com/1"}],
        "infoboxes": [{"content": "Infobox content", "urls": [{"url": "https://wiki.example.com"}]}],
    }
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="test")
    assert "Infobox content" in result
    assert "wiki.example.com" in result


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_max_results_clamped(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"title": f"T{i}", "content": "C", "url": f"https://ex.com/{i}"} for i in range(25)]
    }
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="test", max_results=999)
    assert result.count("https://ex.com/") == 20


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_retry_then_fail(mock_httpx):
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("API down"))
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(query="fail", _retries=1)
    assert "Search error" in result
    assert mock_client.get.call_count == 2


@pytest.mark.anyio
async def test_run_empty_query():
    result = await run(query="")
    assert "empty" in result or "ERROR" in result

    result = await run(query="   ")
    assert "empty" in result or "ERROR" in result


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_invalid_time_range(mock_httpx):
    result = await run(query="test", time_range="century")
    assert "ERROR" in result
    assert "century" in result
    mock_httpx.AsyncClient.assert_not_called()


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_negative_page(mock_httpx):
    result = await run(query="test", page=-1)
    assert "ERROR" in result
    assert "page" in result.lower()
    mock_httpx.AsyncClient.assert_not_called()


@patch("src.tools.web_search.httpx")
@pytest.mark.anyio
async def test_run_zero_page(mock_httpx):
    result = await run(query="test", page=0)
    assert "ERROR" in result
    assert "page" in result.lower()
    mock_httpx.AsyncClient.assert_not_called()
