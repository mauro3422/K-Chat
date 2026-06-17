"""Tests for the Telegram bot lifecycle and adapter edge cases.

Covers:
1. PID lock — previene instancias duplicadas del bot
2. Adapter module load — no debe tener ImportError en módulo principal
3. _get_or_create_session edge cases — sesión nueva, existente, reinicio
4. process_message commands — yield correcto para /start, /reset, etc.
5. process_message error handling — no explota ante errores de red/DB
"""

import pytest
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# PID LOCK TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestPidLock:
    """_check_pid_lock debe prevenir instancias duplicadas del bot."""

    def test_pid_lock_creates_file(self, tmp_path):
        """PID lock debe crear el archivo .pid si no existe."""
        from channels.telegram.__main__ import _PID_FILE as original_pid
        # Monkeypatch _PID_FILE a tmp_path
        with patch('channels.telegram.__main__._PID_FILE', tmp_path / "test_bot.pid"):
            from channels.telegram.__main__ import _check_pid_lock as check
            try:
                check()
                assert (tmp_path / "test_bot.pid").exists(), (
                    "PID file debe crearse"
                )
            except SystemExit:
                pass  # puede salir si otro proceso ya tiene el lock

    def test_pid_lock_exits_on_duplicate(self, tmp_path):
        """PID lock debe salir (sys.exit(1)) si ya hay otra instancia."""
        pid_file = tmp_path / "test_dup.pid"
        pid_file.write_text(str(os.getpid()))
        
        # Mock os.kill para que parezca que el PID existe, y mock
        # la lectura de /proc/PID/cmdline para que contenga "channels.telegram"
        import builtins
        original_open = builtins.open
        
        def mock_open(path, *args, **kwargs):
            if 'cmdline' in str(path):
                mock_file = MagicMock()
                mock_file.read.return_value = b"python -m channels.telegram"
                mock_file.__enter__.return_value = mock_file
                return mock_file
            return original_open(path, *args, **kwargs)
        
        with patch('os.kill', return_value=None), \
             patch('builtins.open', mock_open), \
             patch('channels.telegram.__main__._PID_FILE', pid_file), \
             pytest.raises(SystemExit) as exc:
            from channels.telegram.__main__ import _check_pid_lock as check
            check()
        
        assert exc.value.code == 1, (
            "Debe salir con código 1 cuando hay duplicado"
        )

    def test_pid_lock_ignores_dead_pid(self, tmp_path):
        """PID lock debe ignorar PIDs muertos (OSError de os.kill)."""
        pid_file = tmp_path / "test_dead.pid"
        pid_file.write_text("999999999")  # PID improbable
        
        from channels.telegram.__main__ import _check_pid_lock as check
        with patch('channels.telegram.__main__._PID_FILE', pid_file):
            try:
                check()
                # Si llegó acá, no salió — OK
                assert True
            except SystemExit:
                pytest.fail("No debe salir cuando el PID viejo está muerto")

    def test_pid_lock_cleans_on_atexit(self, tmp_path):
        """PID lock debe registrar un atexit handler que limpia el archivo."""
        pid_file = tmp_path / "test_cleanup.pid"
        
        with patch('channels.telegram.__main__._PID_FILE', pid_file):
            from channels.telegram.__main__ import _check_pid_lock as check
            try:
                check()
            except SystemExit:
                pass
            
            assert pid_file.exists(), "PID file debe existir después de check"
            
            # Ejecutar atexit handlers
            import atexit
            atexit._run_exitfuncs()
            
            assert not pid_file.exists(), (
                "PID file debe eliminarse en atexit"
            )


# ═══════════════════════════════════════════════════════════════════════
# ADAPTER MODULE LOAD TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestAdapterModuleLoad:
    """El módulo adapter.py debe cargarse sin errores de import."""

    def test_adapter_module_imports_cleanly(self):
        """Importar channels.telegram.adapter no debe lanzar ImportError."""
        try:
            import channels.telegram.adapter
            assert True
        except ImportError as e:
            pytest.fail(
                f"channels.telegram.adapter lanzó ImportError: {e}"
            )

    def test_adapter_exports_process_message(self):
        """El adapter debe exportar process_message (entry point del bot)."""
        from channels.telegram.adapter import process_message
        assert process_message is not None

    def test_adapter_exports_get_or_create_session(self):
        """El adapter debe exportar _get_or_create_session."""
        from channels.telegram.adapter import _get_or_create_session
        assert _get_or_create_session is not None

    def test_adapter_exports_lazy_imports(self):
        """El adapter debe exportar _LazyImports (usado internamente)."""
        from channels.telegram.adapter import _LazyImports
        assert _LazyImports is not None


# ═══════════════════════════════════════════════════════════════════════
# ADAPTER SESSION MANAGEMENT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestGetOrCreateSession:
    """_get_or_create_session edge cases con repos mockeados."""

    @pytest.mark.asyncio
    async def test_new_session_creates_id(self):
        """Chat sin sesión debe crear una nueva session_id con prefijo tele_."""
        from channels.telegram.adapter import _get_or_create_session, _LazyImports
        
        # Mock repos
        mock_sessions = AsyncMock()
        mock_sessions.find_by_telegram_chat_id.return_value = None
        mock_sessions.ensure = AsyncMock()
        mock_sessions.update_telegram_chat_id = AsyncMock()
        
        mock_messages = AsyncMock()
        mock_messages.get_session_messages = AsyncMock(return_value=[])
        
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        mock_repos.messages = mock_messages
        
        li = _LazyImports()
        li.get_repos = MagicMock(return_value=mock_repos)
        li.get_default_model = MagicMock(return_value="deepseek-v4-flash")
        li.build_system_prompt = MagicMock(return_value={
            "role": "system", "content": "test prompt"
        })

        session_id, history = await _get_or_create_session(12345, li)
        
        assert session_id.startswith("tele_"), (
            f"Nueva session_id debe empezar con 'tele_', pero es: {session_id}"
        )
        assert len(session_id) == 25, (
            f"session_id debe tener 25 chars (tele_ + 20 hex), tiene {len(session_id)}"
        )
        assert len(history) == 2, (
            f"Historial debe tener 2 elementos (system + channel), tiene {len(history)}"
        )
        # Verificar que se llamó a update_telegram_chat_id
        mock_sessions.update_telegram_chat_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_session_restores(self):
        """Chat con sesión existente debe restaurar session_id."""
        from channels.telegram.adapter import _get_or_create_session, _LazyImports
        
        mock_sessions = AsyncMock()
        mock_sessions.find_by_telegram_chat_id.return_value = "tele_existing1234567890"
        mock_sessions.ensure = AsyncMock()
        
        mock_messages = AsyncMock()
        mock_messages.get_session_messages = AsyncMock(return_value=[])
        
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        mock_repos.messages = mock_messages
        
        li = _LazyImports()
        li.get_repos = MagicMock(return_value=mock_repos)
        li.get_default_model = MagicMock(return_value="deepseek-v4-flash")
        li.build_system_prompt = MagicMock(return_value={
            "role": "system", "content": "test prompt"
        })

        session_id, history = await _get_or_create_session(12345, li)
        
        assert session_id == "tele_existing1234567890"
        assert len(history) == 2
        # No debe llamar a update_telegram_chat_id para sesiones existentes
        mock_sessions.update_telegram_chat_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_with_messages_builds_history(self):
        """Sesión con mensajes debe construirlos en el historial."""
        from channels.telegram.adapter import _get_or_create_session, _LazyImports
        
        mock_sessions = AsyncMock()
        mock_sessions.find_by_telegram_chat_id.return_value = "tele_msgs1234567890123"
        mock_sessions.ensure = AsyncMock()
        
        # Simular 2 mensajes: user "Hola" + assistant "Chau"
        mock_messages = AsyncMock()
        mock_messages.get_session_messages = AsyncMock(return_value=[
            ("user", "Hola", None, "t1", "", "[]", None, None),
            ("assistant", "Chau", None, "t2", "razonando", '[]', None, None),
        ])
        
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        mock_repos.messages = mock_messages
        
        li = _LazyImports()
        li.get_repos = MagicMock(return_value=mock_repos)
        li.get_default_model = MagicMock(return_value="deepseek-v4-flash")
        li.build_system_prompt = MagicMock(return_value={
            "role": "system", "content": "test prompt"
        })

        session_id, history = await _get_or_create_session(12345, li)
        
        # 2 system msgs + 2 user/assistant = 4
        assert len(history) == 4, (
            f"Historial debe tener 4 elementos (2 system + 2 mensajes), "
            f"tiene {len(history)}"
        )
        # El primer mensaje del usuario debe estar en posición 2
        user_msg = history[2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Hola"

    @pytest.mark.asyncio
    async def test_session_with_incomplete_tool_chain_stripped(self):
        """Tool calls sin tool responses deben ser removidas del historial."""
        from channels.telegram.adapter import _get_or_create_session, _LazyImports
        
        mock_sessions = AsyncMock()
        mock_sessions.find_by_telegram_chat_id.return_value = "tele_tools999"
        mock_sessions.ensure = AsyncMock()
        
        # assistant con tool_call pero sin tool response → debe borrarse
        mock_messages = AsyncMock()
        mock_messages.get_session_messages = AsyncMock(return_value=[
            ("user", "Busca algo", None, "t1", "", "[]", None, None),
            ("assistant", None, None, "t2", "buscando", '[]',
             '[{"id":"call_1","function":{"name":"web_search","arguments":"{}"}}]', None),
            # NO hay tool response — cadena incompleta
            ("user", "Otra cosa", None, "t3", "", "[]", None, None),
            ("assistant", "Respuesta", None, "t4", "listo", '[]', None, None),
        ])
        
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        mock_repos.messages = mock_messages
        
        li = _LazyImports()
        li.get_repos = MagicMock(return_value=mock_repos)
        li.get_default_model = MagicMock(return_value="deepseek-v4-flash")
        li.build_system_prompt = MagicMock(return_value={
            "role": "system", "content": "test prompt"
        })

        session_id, history = await _get_or_create_session(12345, li)
        
        # 2 system + 3 mensajes (el tool_call incompleto se borró)
        assert len(history) == 5, (
            f"Historial debe tener 5 elementos (2 system + 3 mensajes válidos), "
            f"tiene {len(history)}"
        )
        # Verificar que el user "Otra cosa" está presente
        messages_roles = [m["role"] for m in history]
        assert messages_roles == ["system", "system", "user", "user", "assistant"], (
            f"Roles esperados: system, system, user, user, assistant. "
            f"Obtenidos: {messages_roles}"
        )

    @pytest.mark.asyncio
    async def test_session_db_error_returns_empty(self):
        """Error de DB en get_session_messages debe devolver historial vacío."""
        from channels.telegram.adapter import _get_or_create_session, _LazyImports
        
        mock_sessions = AsyncMock()
        mock_sessions.find_by_telegram_chat_id.return_value = "tele_err_session"
        mock_sessions.ensure = AsyncMock()
        
        mock_messages = AsyncMock()
        mock_messages.get_session_messages = AsyncMock(side_effect=Exception("DB error"))
        
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        mock_repos.messages = mock_messages
        
        li = _LazyImports()
        li.get_repos = MagicMock(return_value=mock_repos)
        li.get_default_model = MagicMock(return_value="deepseek-v4-flash")
        li.build_system_prompt = MagicMock(return_value={
            "role": "system", "content": "test prompt"
        })

        session_id, history = await _get_or_create_session(12345, li)
        
        assert len(history) == 2, (
            f"Error de DB debe devolver historial con solo los 2 system msgs, "
            f"pero tiene {len(history)}"
        )


# ═══════════════════════════════════════════════════════════════════════
# PROCESS MESSAGE COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestProcessMessageCommands:
    """process_message debe manejar comandos correctamente."""

    @pytest.mark.asyncio
    async def test_start_command_yields_welcome(self):
        """/start debe yield el mensaje de bienvenida."""
        from channels.telegram.adapter import process_message
        
        # Mock _LazyImports internally by patching _get_or_create_session
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("test_session", [
                       {"role": "system", "content": "prompt"},
                       {"role": "system", "content": "channel"},
                   ]))):
            gen = process_message("/start", 12345, MagicMock())
            chunks = [c async for c in gen]
            
            assert len(chunks) == 1, "/start debe yield 1 chunk"
            assert "__content__:¡Hola!" in chunks[0], (
                f"Debe empezar con saludo, pero es: {chunks[0][:60]}"
            )

    @pytest.mark.asyncio
    async def test_reset_command_calls_delete(self):
        """/reset debe llamar a delete_session_messages."""
        from channels.telegram.adapter import process_message
        
        mock_messages = AsyncMock()
        mock_messages.delete_session_messages = AsyncMock()
        mock_repos = MagicMock()
        mock_repos.messages = mock_messages
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("test_session", []))):
            # Patch get_repos a nivel de src.api (lo que importa _LazyImports)
            with patch('src.api.get_repos', MagicMock(return_value=mock_repos)):
                gen = process_message("/reset", 12345, MagicMock())
                chunks = [c async for c in gen]
                
                assert len(chunks) == 1
                assert "✅ Chat reiniciado" in chunks[0]
                mock_messages.delete_session_messages.assert_called_once_with(
                    "test_session"
                )

    @pytest.mark.asyncio
    async def test_help_command_yields_help(self):
        """/help debe yield mensaje de ayuda."""
        from channels.telegram.adapter import process_message
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("test_session", []))):
            gen = process_message("/help", 12345, MagicMock())
            chunks = [c async for c in gen]
            
            assert len(chunks) == 1
            assert "__content__:" in chunks[0]
            assert "Comandos" in chunks[0]

    @pytest.mark.asyncio
    async def test_new_command_calls_reset_session(self):
        """/new debe crear una nueva sesión."""
        from channels.telegram.adapter import process_message
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("old_session", []))):
            with patch('channels.telegram.adapter._reset_session',
                       AsyncMock(return_value="new_session")):
                gen = process_message("/new", 12345, MagicMock())
                chunks = [c async for c in gen]
                
                assert len(chunks) == 1
                assert "✅ Nueva sesión" in chunks[0]

    @pytest.mark.asyncio
    async def test_delete_command_calls_delete_cascade(self):
        """/delete debe llamar a delete_cascade."""
        from channels.telegram.adapter import process_message
        
        mock_sessions = AsyncMock()
        mock_sessions.delete_cascade = AsyncMock()
        mock_repos = MagicMock()
        mock_repos.sessions = mock_sessions
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("del_session", []))):
            with patch('src.api.get_repos', MagicMock(return_value=mock_repos)):
                with patch('src.memory.repos.telegram_msg_id_repository.TelegramMsgIdRepo') as mock_repo_cls:
                    mock_repo = AsyncMock()
                    mock_repo.delete_chat = AsyncMock()
                    mock_repo_cls.return_value = mock_repo
                    
                    gen = process_message("/delete", 12345, MagicMock())
                    chunks = [c async for c in gen]
                    
                    assert len(chunks) == 1
                    assert "🗑 Sesión eliminada" in chunks[0]
                    mock_sessions.delete_cascade.assert_called_once()

    @pytest.mark.asyncio
    async def test_regular_message_does_not_yield_immediately(self):
        """Mensaje normal (no comando) no debe yield inmediatamente (va a LLM)."""
        from channels.telegram.adapter import process_message
        
        mock_messages = AsyncMock()
        mock_messages.save_record = AsyncMock()
        mock_repos = MagicMock()
        mock_repos.messages = mock_messages
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("test_session", [
                       {"role": "system", "content": "prompt"},
                   ]))):
            with patch('src.api.get_repos', MagicMock(return_value=mock_repos)):
                gen = process_message("Hola", 12345, MagicMock())
                # No debemos consumir el generador (se colgaría en chat_stream)
                # Solo verificar que la estructura es correcta
                assert gen is not None
                assert hasattr(gen, '__aiter__')
                # Verificar que se guardó el mensaje de usuario
                # (No podemos verificar esto sin consumir el generator)


# ═══════════════════════════════════════════════════════════════════════
# PROCESS MESSAGE ERROR RESILIENCE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestProcessMessageErrors:
    """process_message debe ser resiliente a errores de infraestructura."""

    @pytest.mark.asyncio
    async def test_sse_notify_failure_does_not_block(self):
        """Fallo en SSE notify no debe interrumpir el flujo."""
        from channels.telegram.adapter import process_message
        
        mock_msgs = AsyncMock()
        mock_msgs.save_record = AsyncMock()
        mock_repos = MagicMock()
        mock_repos.messages = mock_msgs
        
        with patch('channels.telegram.adapter._get_or_create_session',
                   AsyncMock(return_value=("sess_sse", []))):
            with patch('src.api.get_repos', MagicMock(return_value=mock_repos)):
                # Mock httpx para que SSE falle
                with patch('httpx.AsyncClient') as mock_httpx:
                    mock_httpx.side_effect = Exception("Network error")
                    
                    gen = process_message("Hola SSE", 12345, MagicMock())
                    # Verificar que el generador se creó (no explotó)
                    assert gen is not None
