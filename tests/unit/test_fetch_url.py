import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock


from src.tools.fetch_url import run, DEFINITION


SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body>
<nav>nav stuff</nav>
<article>
<h1>Hello World</h1>
<p>This is a test paragraph.</p>
</article>
<footer>footer text</footer>
</body></html>"""


@pytest.mark.anyio
async def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "fetch_url"
    props = DEFINITION["function"]["parameters"]["properties"]
    assert "url" in props
    assert "max_chars" in props
    assert DEFINITION["function"]["parameters"]["required"] == ["url"]


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_basic_page(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = SAMPLE_HTML.encode()
    mock_resp.text = SAMPLE_HTML
    mock_resp.url = "https://example.com/test"
    mock_resp.history = []
    mock_resp.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/test")
    assert "Test Page" in result
    assert "Hello World" in result
    assert "This is a test paragraph" in result
    assert "nav" not in result or "nav stuff" not in result
    assert "footer" not in result or "footer text" not in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_url_normalizes_scheme(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"<html><body><p>test</p></body></html>"
    mock_resp.text = "<html><body><p>test</p></body></html>"
    mock_resp.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    await run(url="example.com/test")
    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://")


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_binary_file(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.content = b"\x89PNG"
    mock_resp.url = "https://example.com/image.png"
    mock_resp.history = []
    mock_resp.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/image.png")
    assert "ERROR" in result or "binary" in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_http_error(mock_httpx):
    from httpx import HTTPStatusError

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status.side_effect = HTTPStatusError("404", request=MagicMock(), response=mock_resp)
    mock_resp.headers = {"content-type": "text/html"}
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/404")
    assert "ERROR" in result
    assert "404" in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_timeout(mock_httpx):
    from httpx import TimeoutException

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=TimeoutException("timeout"))
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/slow")
    assert "ERROR" in result
    assert "Timeout" in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_max_chars_clamped(mock_httpx):
    long_text = "<html><body>" + " ".join(["word"] * 20000) + "</body></html>"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = long_text.encode()
    mock_resp.text = long_text
    mock_resp.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/long", max_chars=500)
    assert "truncated" in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_with_redirect(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"<html><body><p>redirected</p></body></html>"
    mock_resp.text = "<html><body><p>redirected</p></body></html>"
    mock_resp.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)

    result = await run(url="https://example.com/redirect")
    assert "redirected" in result
    assert mock_httpx.AsyncClient.call_args[1]["follow_redirects"] is True


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_rejects_ftp(mock_httpx):
    result = await run(url="ftp://files.example.com/file.txt")
    assert "Unsupported scheme" in result or "ERROR" in result
    mock_httpx.AsyncClient.assert_not_called()


@pytest.mark.anyio
async def test_fetch_empty_url():
    result = await run(url="")
    assert "URL is empty" in result or "ERROR" in result


@patch("src.tools.fetch_url.httpx")
@pytest.mark.anyio
async def test_fetch_rejects_unknown_scheme(mock_httpx):
    result = await run(url="gopher://example.com/file")
    assert "Unsupported scheme" in result or "ERROR" in result
    mock_httpx.AsyncClient.assert_not_called()
