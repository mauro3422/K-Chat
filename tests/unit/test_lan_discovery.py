from __future__ import annotations

import json
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.coordination.lan_discovery import LanDiscovery


def _config(**overrides):
    values = {
        "cluster_name": "kairos",
        "node_id": "windows-primary",
        "node_role": "primary",
        "port": 8000,
        "lan_discovery_group": "239.255.42.99",
        "lan_discovery_port": 42429,
        "lan_discovery_interval": 5.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _packet(**overrides) -> bytes:
    values = {
        "service": "kairos",
        "version": 1,
        "cluster": "kairos",
        "node_id": "linux-secondary",
        "role": "secondary",
        "port": 8000,
    }
    values.update(overrides)
    return json.dumps(values).encode()


def test_discovery_registers_private_source_address_instead_of_payload_url() -> None:
    discovered: list[tuple[str, float]] = []
    discovery = LanDiscovery(_config(), on_peer=lambda url, seen: discovered.append((url, seen)))

    peer = discovery.handle_datagram(_packet(base_url="http://evil.example"), "192.168.1.40", now=12.0)

    assert peer == "http://192.168.1.40:8000"
    assert discovered == [(peer, 12.0)]


def test_discovery_rejects_other_clusters_public_sources_and_self() -> None:
    discovered: list[str] = []
    discovery = LanDiscovery(_config(), on_peer=lambda url, _seen: discovered.append(url))

    assert discovery.handle_datagram(_packet(cluster="other"), "192.168.1.40") is None
    assert discovery.handle_datagram(_packet(), "8.8.8.8") is None
    assert discovery.handle_datagram(_packet(node_id="windows-primary"), "192.168.1.40") is None
    assert discovered == []


def test_discovery_rejects_invalid_payload_and_port() -> None:
    discovery = LanDiscovery(_config(), on_peer=lambda _url, _seen: None)

    assert discovery.handle_datagram(b"not-json", "192.168.1.40") is None
    assert discovery.handle_datagram(_packet(port=70000), "192.168.1.40") is None


def test_discovery_normalizes_missing_cluster_name() -> None:
    discovery = LanDiscovery(_config(cluster_name=None), on_peer=lambda _url, _seen: None)

    payload = json.loads(discovery.announcement())

    assert payload["cluster"] == "kairos"


def test_discovery_uses_resolved_lan_interface_for_multicast() -> None:
    listener = MagicMock()
    sender = MagicMock()
    discovery = LanDiscovery(
        _config(),
        on_peer=lambda _url, _seen: None,
        lan_ip_resolver=lambda: "192.168.1.35",
    )

    with patch("src.coordination.lan_discovery.socket.socket", side_effect=[listener, sender]):
        discovery._open_sockets()

    interface = socket.inet_aton("192.168.1.35")
    listener.setsockopt.assert_any_call(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        socket.inet_aton("239.255.42.99") + interface,
    )
    sender.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
