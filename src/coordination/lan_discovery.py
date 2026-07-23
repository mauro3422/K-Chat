"""Zero-configuration discovery for Kairos nodes on the local network."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from collections.abc import Callable
from typing import Any

from src.config_loader import Config
from src.coordination.lan_addressing import is_lan_address, normalize_lan_peer_url

logger = logging.getLogger(__name__)


def detect_lan_ip() -> str:
    """Return the address selected by the OS for LAN traffic."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = str(probe.getsockname()[0])
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        probe.close()

    try:
        address = socket.gethostbyname(socket.gethostname())
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    return "127.0.0.1"


class LanDiscovery:
    """Advertise this node and discover same-cluster peers over multicast UDP."""

    def __init__(
        self,
        config: Config,
        *,
        on_peer: Callable[[str, float], None],
        lan_ip_resolver: Callable[[], str] = detect_lan_ip,
    ) -> None:
        self._config = config
        self._on_peer = on_peer
        self._lan_ip_resolver = lan_ip_resolver
        self._stop = asyncio.Event()
        self._listener: socket.socket | None = None
        self._sender: socket.socket | None = None

    @property
    def group(self) -> str:
        return str(getattr(self._config, "lan_discovery_group", "239.255.42.99"))

    @property
    def port(self) -> int:
        return int(getattr(self._config, "lan_discovery_port", 42429))

    @property
    def interval(self) -> float:
        return max(1.0, float(getattr(self._config, "lan_discovery_interval", 5.0)))

    def announcement(self) -> bytes:
        payload = {
            "service": "kairos",
            "version": 1,
            "cluster": str(getattr(self._config, "cluster_name", "kairos") or "kairos"),
            "node_id": str(getattr(self._config, "node_id", "")),
            "role": str(getattr(self._config, "node_role", "secondary")),
            "port": int(getattr(self._config, "port", 8000)),
            "timestamp": time.time(),
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def handle_datagram(self, data: bytes, source_address: str, *, now: float | None = None) -> str | None:
        """Validate one announcement and register its source as a peer."""
        if not is_lan_address(source_address):
            return None
        try:
            payload: Any = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("service") != "kairos" or payload.get("version") != 1:
            return None
        local_cluster = str(getattr(self._config, "cluster_name", "kairos") or "kairos")
        if str(payload.get("cluster", "")) != local_cluster:
            return None
        if str(payload.get("node_id", "")) == str(getattr(self._config, "node_id", "")):
            return None
        try:
            port = int(payload.get("port", 0))
        except (TypeError, ValueError):
            return None
        if not 1 <= port <= 65535:
            return None
        peer_url = f"http://{source_address}:{port}"
        self._on_peer(peer_url, time.monotonic() if now is None else now)
        return peer_url

    def _open_sockets(self) -> None:
        lan_ip = self._lan_ip_resolver()
        try:
            interface = socket.inet_aton(lan_ip)
        except OSError:
            interface = socket.inet_aton("0.0.0.0")

        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("", self.port))
        membership = socket.inet_aton(self.group) + interface
        listener.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        listener.setblocking(False)

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
        sender.setblocking(False)
        self._listener = listener
        self._sender = sender
        logger.info("LAN discovery listening on %s:%d via %s", self.group, self.port, lan_ip)

    async def run(self) -> None:
        """Run until ``stop`` is called; socket failures remain non-fatal."""
        self._open_sockets()
        assert self._listener is not None and self._sender is not None
        loop = asyncio.get_running_loop()
        next_announcement = 0.0
        try:
            while not self._stop.is_set():
                now = loop.time()
                if now >= next_announcement:
                    await loop.sock_sendto(self._sender, self.announcement(), (self.group, self.port))
                    next_announcement = now + self.interval
                timeout = max(0.1, min(1.0, next_announcement - loop.time()))
                try:
                    data, address = await asyncio.wait_for(loop.sock_recvfrom(self._listener, 4096), timeout)
                except asyncio.TimeoutError:
                    continue
                self.handle_datagram(data, str(address[0]))
        except asyncio.CancelledError:
            raise
        except OSError as exc:
            logger.warning("LAN discovery stopped: %s", exc)
        finally:
            self.close()

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        for sock in (self._listener, self._sender):
            if sock is not None:
                sock.close()
        self._listener = None
        self._sender = None
