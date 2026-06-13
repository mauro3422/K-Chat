import ipaddress
import logging
import os
import re
import socket
import time
from typing import Any
from urllib.parse import urlparse
import httpx
from httpx import ConnectError, HTTPStatusError, RequestError, TimeoutException
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Kairos/1.0"
MAX_SIZE = 500_000
MIN_CHARS = 500
MAX_CHARS = 50000
REQUEST_TIMEOUT = 15.0

# Module-level constant, never mutated after init — thread-safe
DEFINITION = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": "Fetch and read the content of a web page. Returns the page title and extracted text content. Use this to read articles, documentation, or any web page in full.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch (including https://)"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of text to return (default: 10000, max: 50000)",
                    "default": 10000
                }
            },
            "required": ["url"]
        }
    }
}

# Module-level constant, never mutated after init — thread-safe
BINARY_EXTENSIONS = frozenset({
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flv",
    ".exe", ".dll", ".bin", ".deb", ".rpm", ".apk",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
})


def _looks_binary(url: str, content_type: str) -> bool:
    ext = re.search(r"\.(\w+)$", url.split("?")[0].rstrip("/"))
    if ext and f".{ext.group(1).lower()}" in BINARY_EXTENSIONS:
        return True
    if content_type and not content_type.startswith(("text/", "application/json", "application/xml", "application/xhtml")):
        return True
    return False


def _extract_text(html_content: str) -> tuple[str, str]:
    from lxml import html as lxml_html

    doc = lxml_html.fromstring(html_content)
    title = doc.findtext(".//title", "").strip()

    for tag in doc.xpath("//script | //style | //nav | //footer | //header | //aside"):
        tag.getparent().remove(tag)

    body = doc.find("body")
    if body is None:
        body = doc

    texts = []
    for el in body.iter():
        tag = el.tag if hasattr(el, "tag") else ""
        text = (el.text or "").strip()
        if text and tag not in ("script", "style"):
            texts.append(text)
        tail = (el.tail or "").strip()
        if tail:
            texts.append(tail)

    raw = "\n".join(texts)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return title, raw.strip()


def _skip_ssrf(config=None) -> bool:
    from src.config_loader import DEFAULT_CONFIG
    cfg = config or DEFAULT_CONFIG
    return cfg.testing


def _deny_private_ip(url: str) -> str | None:
    if _skip_ssrf():
        return None
    hostname = urlparse(url).hostname
    if not hostname:
        return "[ERROR] Invalid URL (could not extract hostname)."
    try:
        ip = socket.getaddrinfo(hostname, None)[0][4][0]
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return f"[ERROR] Access denied. Connections to private or local addresses are not allowed ({ip})."
    except (socket.gaierror, OSError, IndexError):
        return "[ERROR] Could not resolve the hostname of the URL."
    return None


def _do_fetch(url: str) -> httpx.Response:
    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp


def _check_redirect_ssrf(resp: httpx.Response) -> str | None:
    for redirect_response in resp.history:
        redirect_err = _deny_private_ip(str(redirect_response.url))
        if redirect_err:
            return redirect_err
    if resp.url:
        ssrf_err = _deny_private_ip(str(resp.url))
        if ssrf_err:
            return ssrf_err
    return None


def _validate_response(url: str, resp: httpx.Response, max_chars: int) -> str | None:
    ct = resp.headers.get("content-type", "")
    if _looks_binary(url, ct):
        return f"[ERROR] {url} appears to be a binary file (content-type: {ct}). Only web pages can be read."
    if len(resp.content) > MAX_SIZE:
        logger.warning("URL too large: %s (%d bytes, max %d)", url, len(resp.content), MAX_SIZE)
        return f"[ERROR] {url} is too large ({len(resp.content)} bytes, max {MAX_SIZE})."
    return None


def _format_output(url: str, status_code: int, title: str, text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[...truncated to {max_chars} characters. Use a larger max_chars value if needed.]"
    out = []
    if title:
        out.append(f"=== {title} ===")
    out.append(f"URL: {url}")
    out.append(f"Status: {status_code}")
    out.append("")
    out.append(text)
    return "\n".join(out)


def _try_fetch(url: str, max_chars: int) -> str:
    resp = _do_fetch(url)
    ssrf_err = _check_redirect_ssrf(resp)
    if ssrf_err:
        return ssrf_err
    validate_err = _validate_response(url, resp, max_chars)
    if validate_err:
        return validate_err
    title, text = _extract_text(resp.text)
    if not text:
        logger.warning("No text extracted from %s", url)
        return f"[ERROR] Could not extract content from {url}. The page may require JavaScript."
    return _format_output(url, resp.status_code, title, text, max_chars)


def _fetch_with_retry(url: str, max_chars: int, _retries: int, **kwargs: Any) -> str | None:
    for attempt in range(_retries + 1):
        try:
            return _try_fetch(url, max_chars)
        except TimeoutException:
            logger.warning("Timeout fetching %s", url)
            if attempt < _retries:
                time.sleep(1)
            else:
                return f"[ERROR] Timeout while trying to access {url}."
        except HTTPStatusError as e:
            logger.warning("HTTP %d fetching %s", e.response.status_code, url)
            return f"[ERROR] {url} returned HTTP {e.response.status_code}."
        except (ConnectError, RequestError):
            logger.warning("Connection error fetching %s", url)
            return f"[ERROR] Could not connect to {url}."
        except Exception as e:
            logger.warning("Error fetching %s: %s", url, e)
            if attempt < _retries:
                time.sleep(1)
            else:
                return f"[ERROR] Error processing {url}."


def run(**kwargs: Any) -> str | None:
    url = kwargs.get("url") or kwargs.get("link") or kwargs.get("page_url", "")
    max_chars = int(kwargs.get("max_chars", kwargs.get("max", kwargs.get("max_length", 10000))))
    _retries = int(kwargs.get("_retries", 1))
    max_chars = min(max(max_chars, MIN_CHARS), MAX_CHARS)

    url = url.strip()
    if not url:
        return "[ERROR] The URL is empty. Provide a valid URL (e.g. https://example.com)."
    scheme_end = url.find("://")
    if scheme_end != -1:
        scheme = url[:scheme_end].lower()
        if scheme not in ("http", "https"):
            return f"[ERROR] Unsupported scheme '{scheme}://'. Only HTTP and HTTPS are supported."
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url

    ssrf_err = _deny_private_ip(url)
    if ssrf_err:
        return ssrf_err

    return _fetch_with_retry(url, max_chars, _retries)
