"""Error handler — classifies Telegram API errors and decides recovery.

Handles common Telegram Bot API errors:

- ``400`` — Bad Request (various causes, classified by description)
- ``401`` — Unauthorized (token invalid or revoked)
- ``403`` — Forbidden (bot blocked by user)
- ``404`` — Not Found (chat or message not found)
- ``429`` — Too Many Requests (rate limited)
- ``409`` — Conflict (webhook conflict)
- Network errors (timeout, connection reset)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from channels.telegram.protocols import RecoveryAction

logger = logging.getLogger(__name__)


class TelegramErrorHandler:
    """Classifies Telegram API errors and returns recovery actions."""

    async def classify(
        self, error: Exception, context: dict | None = None,
    ) -> RecoveryAction:
        ctx = context or {}

        # ── HTTPX errors (network level) ────────────────────────────────
        if isinstance(error, httpx.TimeoutException):
            logger.warning("TG timeout: %s", error)
            return RecoveryAction(retry=True, wait_seconds=2.0)

        if isinstance(error, httpx.NetworkError):
            logger.warning("TG network: %s", error)
            return RecoveryAction(retry=True, wait_seconds=5.0)

        # ── HTTP status errors (application level) ──────────────────────
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            body = ""
            try:
                body = error.response.text[:300]
            except Exception:
                pass

            if status == 429:
                # Rate limited
                retry_after = 3
                try:
                    retry_after = int(error.response.json().get("parameters", {}).get("retry_after", 3))
                except Exception:
                    pass
                logger.warning("TG 429 (retry_after=%d): %s", retry_after, body[:100])
                return RecoveryAction(
                    retry=True, wait_seconds=float(retry_after), fallback_text=None,
                )

            if status == 400:
                # Bad Request — various causes
                if "message is not modified" in body.lower():
                    # This is benign — the content hasn't changed
                    logger.debug("TG 400: message not modified (benign)")
                    return RecoveryAction(retry=False, abort=False)
                if "too long" in body.lower():
                    # Message exceeds 4096 chars
                    logger.warning("TG 400: message too long")
                    return RecoveryAction(
                        retry=False, abort=False,
                        fallback_text="⚠️ [Message truncated]",
                    )
                if "can't parse entities" in body.lower() or "can't parse" in body.lower():
                    # Markdown parse error — retry with plain text
                    logger.warning("TG 400: can't parse entities - retrying as plain text")
                    return RecoveryAction(
                        retry=True, wait_seconds=0, fallback_text=None,
                    )
                if "message can't be edited" in body.lower():
                    # Message too old to edit (Telegram limit: 48h)
                    logger.warning("TG 400: message can't be edited (too old?)")
                    return RecoveryAction(retry=False, abort=False)
                if "message to edit not found" in body.lower():
                    logger.warning("TG 400: message to edit not found")
                    return RecoveryAction(retry=False, abort=False)
                # Other 400 — log and skip
                logger.warning("TG 400: %s", body[:150])
                return RecoveryAction(retry=False, abort=False)

            if status == 403:
                # Bot blocked by user
                logger.warning("TG 403: bot blocked by user? %s", body[:100])
                return RecoveryAction(retry=False, abort=True)

            if status == 404:
                # Chat or message not found
                target = ctx.get("message_id", "?")
                logger.warning("TG 404: message %s not found", target)
                return RecoveryAction(retry=False, abort=False)

            if status == 409:
                # Webhook conflict
                logger.warning("TG 409: webhook conflict")
                return RecoveryAction(retry=True, wait_seconds=1.0)

            if status in (401, 500, 502, 503):
                # Auth / server errors — retry with backoff
                logger.warning("TG %d: %s", status, body[:100])
                return RecoveryAction(retry=True, wait_seconds=3.0)

            # Unknown HTTP error
            logger.warning("TG HTTP %d (unhandled): %s", status, body[:150])
            return RecoveryAction(retry=False, abort=True)

        # ── Unknown errors ──────────────────────────────────────────────
        logger.exception("TG unknown error: %s", error)
        return RecoveryAction(retry=False, abort=True)
