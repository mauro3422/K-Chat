"""Standard-library HTTP signing helpers for Kairos operational entry points."""

from __future__ import annotations

import os
import urllib.request
from typing import Any

from src.coordination.lan_auth import (
    LanRequestSigner,
    LanRequestSignerProtocol,
    encode_json_body,
    is_sensitive_lan_request,
    request_path,
)


def signer_from_environment(
    default_node_id: str,
) -> LanRequestSignerProtocol | None:
    secret = os.getenv("KAIROS_LAN_SHARED_SECRET", "").strip()
    node_id = (
        os.getenv("KAIROS_LAN_CLIENT_NODE_ID", "").strip()
        or os.getenv("KAIROS_NODE_ID", "").strip()
        or default_node_id
    )
    if not secret:
        return None
    return LanRequestSigner(secret, node_id)


def build_json_request(
    method: str,
    url: str,
    *,
    payload: Any | None = None,
    signer: LanRequestSignerProtocol | None = None,
) -> urllib.request.Request:
    body = encode_json_body(payload) if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    if signer is None:
        if is_sensitive_lan_request(method, url):
            raise RuntimeError(
                "KAIROS_LAN_SHARED_SECRET is required for this LAN operation"
            )
    else:
        headers.update(
            signer.sign_headers(
                method,
                request_path(url),
                body or b"",
            )
        )
    return urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method.upper(),
    )
