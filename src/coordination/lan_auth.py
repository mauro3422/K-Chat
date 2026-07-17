"""Pure LAN request signing and replay-safe verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit


class LanRequestSignerProtocol(Protocol):
    def sign_headers(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        ...


class LanRequestVerifierProtocol(Protocol):
    @property
    def configured(self) -> bool:
        ...

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> "LanAuthResult":
        ...

    def clear(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class LanAuthResult:
    ok: bool
    code: str
    node_id: str = ""


def encode_json_body(payload: Any) -> bytes:
    """Match httpx JSON encoding so the signed bytes equal the transmitted body."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def parse_lan_node_ids(raw: str | None) -> set[str]:
    if not isinstance(raw, str):
        return set()
    return {
        item.strip()
        for item in raw.replace("\n", ",").split(",")
        if item.strip()
    }


def request_path(url_or_path: str) -> str:
    parsed = urlsplit(url_or_path)
    return parsed.path or "/"


def is_sensitive_lan_request(method: str, path: str) -> bool:
    """Return whether an HTTP operation belongs to the protected LAN perimeter."""
    normalized_path = request_path(path)
    normalized_method = method.upper()
    if normalized_path.startswith("/api/memory/"):
        return True
    if normalized_path.startswith("/api/node/memory/"):
        return True
    if normalized_path.startswith("/api/node/embeddings/"):
        return True
    if normalized_path in {
        "/api/node/sessions",
        "/api/node/sync/status",
        "/api/node/diagnostics",
    }:
        return True
    return (normalized_method, normalized_path) in {
        ("POST", "/api/node/heartbeat"),
        ("POST", "/api/node/promote"),
        ("POST", "/api/node/demote"),
        ("POST", "/api/node/event"),
    }


def _canonical_message(
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    node_id: str,
    body: bytes,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join(
        (
            method.upper(),
            request_path(path),
            timestamp,
            nonce,
            node_id,
            body_hash,
        )
    ).encode("utf-8")


class LanRequestSigner:
    """Create HMAC-SHA256 headers without retaining request payloads."""

    def __init__(
        self,
        secret: str,
        node_id: str,
        *,
        clock: Callable[[], float] = time.time,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not secret:
            raise ValueError("LAN shared secret is required")
        if not node_id:
            raise ValueError("LAN signer node_id is required")
        self._secret = secret.encode("utf-8")
        self._node_id = node_id
        self._clock = clock
        self._nonce_factory = nonce_factory or (lambda: secrets.token_hex(16))

    def sign_headers(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        timestamp_text = str(int(self._clock()) if timestamp is None else int(timestamp))
        nonce_text = nonce or self._nonce_factory()
        message = _canonical_message(
            method,
            path,
            timestamp_text,
            nonce_text,
            self._node_id,
            body,
        )
        signature = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        return {
            "X-Kairos-Node-Id": self._node_id,
            "X-Kairos-Timestamp": timestamp_text,
            "X-Kairos-Nonce": nonce_text,
            "X-Kairos-Signature": signature,
        }


class LanRequestVerifier:
    """Verify LAN signatures and reject replay within a bounded time window."""

    def __init__(
        self,
        secret: str,
        allowed_node_ids: set[str],
        *,
        window_seconds: int = 30,
        nonce_capacity: int = 4096,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret.encode("utf-8") if secret else b""
        self._allowed_node_ids = frozenset(allowed_node_ids)
        self._window_seconds = max(1, int(window_seconds))
        self._nonce_capacity = max(1, int(nonce_capacity))
        self._clock = clock
        self._nonces: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._nonce_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._secret and self._allowed_node_ids)

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        if value is None:
            expected = name.lower()
            value = next(
                (
                    candidate
                    for key, candidate in headers.items()
                    if str(key).lower() == expected
                ),
                None,
            )
        return str(value or "").strip()

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> LanAuthResult:
        if not self.configured:
            return LanAuthResult(False, "configuration_missing")

        node_id = self._header(headers, "X-Kairos-Node-Id")
        timestamp_text = self._header(headers, "X-Kairos-Timestamp")
        nonce = self._header(headers, "X-Kairos-Nonce")
        signature = self._header(headers, "X-Kairos-Signature")
        if not all((node_id, timestamp_text, nonce, signature)):
            return LanAuthResult(False, "missing_credentials")
        if node_id not in self._allowed_node_ids:
            return LanAuthResult(False, "node_not_allowed", node_id)
        if len(node_id) > 128 or not 16 <= len(nonce) <= 128:
            return LanAuthResult(False, "invalid_credentials", node_id)

        try:
            timestamp = int(timestamp_text)
        except ValueError:
            return LanAuthResult(False, "invalid_timestamp", node_id)

        now = self._clock()
        delta = now - timestamp
        if delta > self._window_seconds:
            return LanAuthResult(False, "timestamp_expired", node_id)
        if delta < -self._window_seconds:
            return LanAuthResult(False, "timestamp_in_future", node_id)

        expected = hmac.new(
            self._secret,
            _canonical_message(
                method,
                path,
                timestamp_text,
                nonce,
                node_id,
                body,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return LanAuthResult(False, "invalid_signature", node_id)

        nonce_key = (node_id, nonce)
        with self._nonce_lock:
            self._remove_expired(now)
            if nonce_key in self._nonces:
                return LanAuthResult(False, "nonce_replayed", node_id)
            if len(self._nonces) >= self._nonce_capacity:
                return LanAuthResult(False, "nonce_capacity_reached", node_id)
            self._nonces[nonce_key] = timestamp + self._window_seconds
        return LanAuthResult(True, "ok", node_id)

    def _remove_expired(self, now: float) -> None:
        expired = [
            key
            for key, expires_at in self._nonces.items()
            if expires_at < now
        ]
        for key in expired:
            self._nonces.pop(key, None)

    def clear(self) -> None:
        with self._nonce_lock:
            self._nonces.clear()

    @property
    def tracked_nonce_count(self) -> int:
        with self._nonce_lock:
            return len(self._nonces)
