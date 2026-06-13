import os
import sys
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SEARXNG_DIR = Path(__file__).parent / "searxng"
SEARXNG_SETTINGS = Path(__file__).parent.parent / ".config" / "searxng" / "settings.yml"
SEARXNG_DEFAULT_SETTINGS = SEARXNG_DIR / "searx" / "settings.yml"
SEARXNG_PORT = int(os.environ.get("SEARXNG_PORT", "8080"))
SEARXNG_AUTO_INSTALL = os.environ.get("SEARXNG_AUTO_INSTALL", "false").lower() in ("1", "true")
_is_running = False
_process = None


def _python() -> str:
    return sys.executable


def _pip() -> str:
    return os.path.join(os.path.dirname(_python()), "pip")


def searxng_is_installed() -> bool:
    try:
        result = subprocess.run(
            [_pip(), "list", "--format=columns"],
            capture_output=True, text=True, timeout=15
        )
        return "searxng" in result.stdout
    except Exception:
        return False


def install_searxng_deps() -> str | None:
    req = SEARXNG_DIR / "requirements.txt"
    if not req.exists():
        return f"requirements.txt no encontrado en {req}"
    try:
        subprocess.run(
            [_pip(), "install", "--break-system-packages", "-r", str(req)],
            check=True, capture_output=True, timeout=120
        )
        subprocess.run(
            [_pip(), "install", "--break-system-packages", str(SEARXNG_DIR)],
            check=True, capture_output=True, timeout=120
        )
        logger.info("SearXNG dependencies installed successfully")
        return None
    except subprocess.CalledProcessError as e:
        return f"Error instalando dependencias de SearXNG: {e.stderr.decode()[:200]}"
    except Exception as e:
        return f"Error: {e}"


def searxng_start() -> str | None:
    global _is_running, _process
    if _is_running:
        return None

    if not searxng_is_installed():
        if not SEARXNG_AUTO_INSTALL:
            return "SearXNG dependencies are not installed. Set SEARXNG_AUTO_INSTALL=1 to install them."
        err = install_searxng_deps()
        if err:
            return err

    settings_path = SEARXNG_SETTINGS if SEARXNG_SETTINGS.exists() else SEARXNG_DEFAULT_SETTINGS

    env = os.environ.copy()
    env["SEARXNG_SETTINGS_PATH"] = str(settings_path)

    try:
        _process = subprocess.Popen(
            [_python(), "-m", "searx.webapp"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _is_running = True
        logger.info("SearXNG started (PID: %s, port: %s)", _process.pid, SEARXNG_PORT)
        return None
    except Exception as e:
        return f"Error starting SearXNG: {e}"


def searxng_stop():
    global _is_running, _process
    if _process:
        try:
            _process.terminate()
            _process.wait(timeout=5)
        except Exception:
            try:
                _process.kill()
            except Exception:
                pass
        _process = None
    _is_running = False
    logger.info("SearXNG stopped")


def searxng_status() -> dict:
    return {
        "running": _is_running,
        "port": SEARXNG_PORT,
        "url": f"http://127.0.0.1:{SEARXNG_PORT}",
        "installed": searxng_is_installed(),
    }
