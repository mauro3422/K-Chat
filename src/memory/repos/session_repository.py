import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, TYPE_CHECKING
from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.memory.repos import Repositories


class SessionRepository(_BaseRepository):

    _did_alter_favorite = False

    async def _ensure_favorite_column(self) -> None:
        if SessionRepository._did_alter_favorite:
            return
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute("PRAGMA table_info(sessions)")
                columns = await cursor.fetchall()
                if any(col[1] == "is_favorite" for col in columns):
                    SessionRepository._did_alter_favorite = True
                    return
                await conn.execute("ALTER TABLE sessions ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.warning("Failed to ensure is_favorite column: %s", e)
        except Exception as e:
            logger.warning("Failed to ensure is_favorite column: %s", e)
        SessionRepository._did_alter_favorite = True

    async def ensure(self, session_id: str) -> None:
        """Create a session row if it does not exist."""
        async with self._transaction() as conn:
            cursor = await conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            if not await cursor.fetchone():
                await conn.execute(
                    "INSERT INTO sessions (session_id, name, created_at) VALUES (?, '', ?)",
                    (session_id, datetime.now().isoformat())
                )

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists without creating it."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        return row is not None

    async def rename(self, session_id: str, name: str) -> None:
        """Rename a session."""
        async with self._transaction() as conn:
            await conn.execute("UPDATE sessions SET name = ? WHERE session_id = ?", (name, session_id))

    async def delete(self, session_id: str, cursor: Any = None) -> None:
        """Delete the session row itself."""
        if cursor is not None:
            await cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        else:
            async with self._transaction() as conn:
                await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    async def delete_cascade(self, session_id: str, repos: "Repositories") -> None:
        """Delete a session and all related rows in one transaction.

        Before cascading the delete, saves a snapshot to
        ``deleted_sessions.db`` so semantic search can still detect
        "ghost" memories from the deleted conversation.
        """
        # ── Step 1: Save snapshot to deleted_sessions.db ──────────────
        try:
            await self._snapshot_to_deleted_db(session_id, repos)
        except Exception:
            logger.exception("Failed to save deleted session snapshot for %s", session_id)
            # Non-fatal: continue with delete even if snapshot fails

        # ── Step 2: Clean up memory.db embeddings for this session ────
        try:
            if repos.memory and repos.memory.vector_store:
                deleted = repos.memory.vector_store.delete_by_source(session_id)
                if deleted:
                    logger.info("Cleaned %d embeddings for deleted session %s",
                                deleted, session_id[:12])
        except Exception:
            logger.exception("Failed to clean embeddings for %s", session_id)

        # ── Step 3: Cascade delete in sessions.db ─────────────────────
        async with self._transaction() as conn:
            await conn.execute("DELETE FROM widget_versions WHERE session_id = ?", (session_id,))
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                await repo.delete_by_session(session_id, conn)
            await self.delete(session_id, cursor=conn)

    # ── Snapshot helper ────────────────────────────────────────────────────

    async def _snapshot_to_deleted_db(
        self, session_id: str, repos: "Repositories",
    ) -> None:
        """Save a summary + embedding of the session before it's deleted.

        This runs OUTSIDE the delete transaction so the snapshot persists
        even if the cascade fails.

        The embedding allows future semantic queries to detect that *something*
        existed about a topic, even though the session itself is gone.
        """
        from src.memory.repos_memory.deleted_session_repo import (
            DeletedSessionEntry,
            DeletedSessionRepository,
        )

        # Fetch session name
        name = ""
        try:
            conn = await self._get_conn()
            row = await (await conn.execute(
                "SELECT name FROM sessions WHERE session_id = ?", (session_id,)
            )).fetchone()
            if row:
                name = row["name"] or ""
        except Exception:
            pass

        # Fetch messages for summary
        messages: list[tuple] = []
        try:
            messages = await repos.messages.get_session_messages(session_id)
        except Exception:
            pass

        message_count = len(messages)

        # Build summary from first user msg + last assistant + last user
        first_user = ""
        last_user = ""
        last_assistant = ""
        for msg in messages:
            role = msg[0] if len(msg) > 0 else ""
            content = msg[1] if len(msg) > 1 else ""
            if role == "user":
                if not first_user:
                    first_user = content[:500]
                last_user = content[:500]
            elif role == "assistant":
                last_assistant = content[:500]

        summary_parts = []
        if first_user:
            summary_parts.append(f"🔹 Primer mensaje: {first_user}")
        if last_assistant:
            summary_parts.append(f"🔸 Última respuesta: {last_assistant}")
        if last_user and last_user != first_user:
            summary_parts.append(f"🔹 Último mensaje: {last_user}")
        if message_count > 0:
            summary_parts.append(f"📊 {message_count} mensajes en total")

        summary = "\n\n".join(summary_parts) if summary_parts else "(sin contenido)"

        # Extract simple topics from messages (heuristic word frequency)
        topics = self._extract_topics(messages)

        # Generate embedding from the summary (for semantic search)
        embedding: list[float] = []
        try:
            from src.memory.embeddings.service import generate_embedding
            embedding = await asyncio.to_thread(generate_embedding, summary)
        except Exception:
            logger.warning(
                "Could not generate embedding for deleted session %s",
                session_id[:12],
            )

        # Save to deleted_sessions.db
        now = datetime.now().isoformat(timespec="seconds")
        entry = DeletedSessionEntry(
            session_id=session_id,
            name=name,
            message_count=message_count,
            summary=summary,
            topics=topics,
            deleted_at=now,
            embedding=embedding,
        )
        deleted_repo = DeletedSessionRepository()
        deleted_repo.save(entry)

    @staticmethod
    def _extract_topics(
        messages: list[tuple],
        max_topics: int = 8,
    ) -> list[str]:
        """Extract simple topic keywords from messages.

        Uses word frequency heuristics (stopwords filtered, short words
        excluded, case-insensitive). No LLM dependency.
        """
        stopwords = {
            "que", "de", "la", "el", "en", "y", "a", "los", "las", "del",
            "para", "por", "con", "una", "un", "es", "lo", "al", "como",
            "mas", "pero", "sus", "le", "ya", "o", "este", "entre", "todo",
            "esta", "desde", "hasta", "porque", "que", "si", "no", "se",
            "me", "te", "mi", "tu", "su", "nos", "les", "the", "and", "that",
            "this", "with", "for", "you", "have", "from", "they", "was",
            "are", "what", "when", "where", "which", "there", "your",
            "puede", "ser", "sido", "muy", "sin", "sobre", "todo", "tambien",
            "cada", "solo", "como", "cuando", "donde", "hubiera", "hecho",
        }
        word_counts: dict[str, int] = {}
        for msg in messages:
            content = (msg[1] or "") if len(msg) > 1 else ""
            words = content.lower().split()
            for w in words:
                w = w.strip(".,;:!?\"'()[]{}¿¡\u2014\u2013-_/@#$%^&*+=<>")
                if len(w) < 4:
                    continue
                if w in stopwords:
                    continue
                word_counts[w] = word_counts.get(w, 0) + 1

        sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])
        return [w for w, c in sorted_words[:max_topics]]

    # ── End of SessionRepository ───────────────────────────────────────────
    async def get_all(self, limit: int = 50) -> list[tuple[Any, ...]]:
        """Return all sessions with summary data (now includes is_favorite)."""
        await self._ensure_favorite_column()
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('''
                SELECT m.session_id,
                       MIN(m.created_at),
                       MAX(m.created_at),
                       COUNT(*),
                       SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END),
                       COALESCE(s.name, ''),
                       s.telegram_chat_id,
                       COALESCE(s.is_favorite, 0)
                FROM messages m
                LEFT JOIN sessions s ON m.session_id = s.session_id
                GROUP BY m.session_id
                ORDER BY MAX(m.created_at) DESC
                LIMIT ?
            ''', (limit,))
            return await cursor.fetchall()
        except Exception:
            logger.exception("Failed to get all sessions")
            return []

    async def set_favorite(self, session_id: str, favorite: bool) -> None:
        """Mark a session as favorite or not."""
        await self._ensure_favorite_column()
        async with self._transaction() as conn:
            await conn.execute(
                "UPDATE sessions SET is_favorite = ? WHERE session_id = ?",
                (1 if favorite else 0, session_id),
            )

    async def get_favorites(self) -> list[dict]:
        """Return all favorited sessions."""
        await self._ensure_favorite_column()
        try:
            conn = await self._get_conn()
            cursor = await conn.execute(
                "SELECT session_id, name, created_at, is_favorite FROM sessions WHERE is_favorite = 1 ORDER BY created_at DESC",
            )
            rows = await cursor.fetchall()
            return [{"session_id": r[0], "name": r[1], "created_at": r[2], "is_favorite": r[3]} for r in rows]
        except Exception:
            logger.exception("Failed to get favorite sessions")
            return []

    async def require_session(self, session_id: str) -> None:
        """Validate that a session exists. Raises ValueError if not found."""
        if not session_id or not session_id.strip():
            raise ValueError("Session not found")
        if not await self.exists(session_id):
            raise ValueError("Session not found")

    # ── Telegram-specific lookup ─────────────────────────────────────

    async def find_by_telegram_chat_id(self, chat_id: int) -> str | None:
        """Get the most recent session_id for a Telegram chat, or None."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('''
                SELECT session_id FROM sessions
                WHERE telegram_chat_id = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (chat_id,))
            row = await cursor.fetchone()
            return row["session_id"] if row else None
        except Exception:
            logger.exception("Failed to find session by telegram_chat_id")
            return None

    async def find_all_by_telegram_chat_id(self, chat_id: int) -> list[tuple[str, str, str]]:
        """Get all session_ids + names for a Telegram chat, newest first."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('''
                SELECT session_id, COALESCE(name, ''), created_at
                FROM sessions
                WHERE telegram_chat_id = ?
                ORDER BY created_at DESC
            ''', (chat_id,))
            rows = await cursor.fetchall()
            return [(r["session_id"], r["name"], r["created_at"]) for r in rows]
        except Exception:
            logger.exception("Failed to find all sessions by telegram_chat_id")
            return []

    async def update_telegram_chat_id(self, session_id: str, chat_id: int) -> None:
        """Set the telegram_chat_id for a session."""
        async with self._transaction() as conn:
            await conn.execute(
                "UPDATE sessions SET telegram_chat_id = ? WHERE session_id = ?",
                (chat_id, session_id),
            )

    async def check_should_rename(self, session_id: str) -> bool:
        """Check if the session should be auto-renamed.

        Triggers for sessions with no name set OR Telegram sessions
        (identified by telegram_chat_id) with only 1 user message.
        """
        try:
            conn = await self._get_conn()
            cursor = await conn.execute(
                "SELECT name, telegram_chat_id FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row:
                name = row["name"] or ""
                is_tg = row["telegram_chat_id"] is not None
                if name == "" or (is_tg and not name):
                    cursor = await conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                        (session_id,),
                    )
                    count_row = await cursor.fetchone()
                    count = count_row[0] if count_row else 0
                    return count == 1
            return False
        except Exception:
            logger.exception("Failed to check should_rename for %s", session_id)
            return False


__all__ = ["SessionRepository"]
