"""FastAPI adapter for the injected LAN authentication verifier."""

from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request

from src.coordination.lan_auth import LanRequestVerifierProtocol


class LanAuthGuard:
    def __init__(
        self,
        verifier: LanRequestVerifierProtocol,
        *,
        testing: bool = False,
        allow_unsigned_loopback: bool = False,
        max_body_bytes: int = 3 * 1024 * 1024,
    ) -> None:
        self._verifier = verifier
        self._testing = testing
        self._allow_unsigned_loopback = allow_unsigned_loopback
        self._max_body_bytes = max(1024, int(max_body_bytes))

    @staticmethod
    def _is_loopback(request: Request) -> bool:
        host = request.client.host if request.client else ""
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
        except ValueError:
            return False

    async def authorize(self, request: Request) -> str:
        content_length = request.headers.get("content-length", "")
        if content_length:
            try:
                if int(content_length) > self._max_body_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={"code": "lan_payload_too_large"},
                    )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "invalid_content_length"},
                ) from exc

        body = await request.body()
        if len(body) > self._max_body_bytes:
            raise HTTPException(
                status_code=413,
                detail={"code": "lan_payload_too_large"},
            )

        if self._testing or (
            self._allow_unsigned_loopback and self._is_loopback(request)
        ):
            request.state.lan_auth_bypassed = True
            request.state.lan_node_id = ""
            return ""

        result = self._verifier.verify(
            request.method,
            request.url.path,
            body,
            request.headers,
        )
        if result.ok:
            request.state.lan_auth_bypassed = False
            request.state.lan_node_id = result.node_id
            return result.node_id

        status_code = {
            "configuration_missing": 503,
            "node_not_allowed": 403,
            "nonce_replayed": 409,
            "nonce_capacity_reached": 503,
        }.get(result.code, 401)
        raise HTTPException(
            status_code=status_code,
            detail={"code": result.code},
        )

    def clear(self) -> None:
        self._verifier.clear()


async def require_lan_request(request: Request) -> str:
    guard = getattr(request.app.state, "lan_auth_guard", None)
    if guard is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "lan_auth_guard_missing"},
        )
    return await guard.authorize(request)


def enforce_lan_node_identity(request: Request, claimed_node_id: str) -> None:
    if bool(getattr(request.state, "lan_auth_bypassed", False)):
        return
    authenticated = str(getattr(request.state, "lan_node_id", "") or "")
    claimed = str(claimed_node_id or "").strip()
    if not claimed:
        raise HTTPException(
            status_code=403,
            detail={"code": "lan_node_identity_required"},
        )
    if not hmac_compare_node_ids(authenticated, claimed):
        raise HTTPException(
            status_code=403,
            detail={"code": "lan_node_identity_mismatch"},
        )


def hmac_compare_node_ids(authenticated: str, claimed: str) -> bool:
    """Use constant-time comparison for authenticated identity equality."""
    import hmac

    return hmac.compare_digest(authenticated, claimed)
