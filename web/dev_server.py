"""Development server launcher for K-Chat."""

from __future__ import annotations

import logging
import socket
import subprocess
import time

import uvicorn

from src.config_loader import load_config

logger = logging.getLogger(__name__)


def _free_port_if_needed(host: str, port: int) -> None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        logger.warning("Port %s is in use, attempting to free it...", port)
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
            time.sleep(1)
        except Exception:
            pass


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    host = cfg.host
    port = cfg.port
    _free_port_if_needed(host, port)
    uvicorn.run(
        "web.server:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=["web", "src"],
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    main()
