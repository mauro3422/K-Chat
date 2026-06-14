from typing import Any, Callable
import logging
from src.context import build_system_prompt
from src.core.history_rebuilder import rebuild_history
from src.memory.repos import Repositories
from src.compressor import compress_history, should_compress

logger = logging.getLogger(__name__)

from src.core.services.protocols import HistoryServiceProtocol

class HistoryService(HistoryServiceProtocol):
    def __init__(self, repos: Repositories | None = None):
        self.repos = repos

    async def rebuild(self, session_id: str, model: str) -> list[dict[str, Any]]:
        if self.repos is None:
             from src.memory.repos import get_repos
             self.repos = get_repos()
        return await rebuild_history(session_id, model, self.repos.messages)

    def get_system_prompt(self, model: str) -> dict[str, Any]:
        return build_system_prompt(model)

    async def compress_if_needed(
        self,
        history: list[dict[str, Any]],
        model: str,
        compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None,
        should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> None:
        _should = should_compress_fn or should_compress
        _compress = compress_fn or compress_history
        if _should(history):
            try:
                await _compress(history, model)
            except Exception as e:
                logger.warning("compress_history failed, history not compressed: %s", e)
