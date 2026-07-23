"""Single, dependency-free policy for dynamic Kairos LAN addresses."""

from __future__ import annotations

import concurrent.futures
import ipaddress
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit


def is_lan_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_link_local or ip.is_loopback)


def normalize_lan_peer_url(raw_url: str) -> str | None:
    """Return canonical literal-LAN HTTP URLs and reject external targets."""
    try:
        parsed = urlsplit(raw_url.strip())
        host = parsed.hostname or ""
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme != "http" or not is_lan_address(host) or port is None:
        return None
    return f"http://{host}:{port}"


def replace_url_host(url: str, host: str, *, default_port: int = 8000) -> str:
    """Preserve a configured HTTP scheme and port while replacing its host."""
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        return f"http://{host}:{default_port}"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, parsed.query, parsed.fragment)).rstrip("/")


def resolve_advertised_base_url(
    configured_url: str,
    bind_host: str,
    port: int,
    *,
    lan_ip_resolver: Callable[[], str],
) -> str:
    """Resolve this node's address without retaining a stale DHCP lease.

    A non-literal hostname remains an explicit operator choice. A literal LAN IP
    that no longer matches the active LAN interface is replaced in-memory with
    the currently detected address.
    """
    detected_host = lan_ip_resolver().strip()
    configured = configured_url.strip().rstrip("/")
    if configured:
        try:
            parsed = urlsplit(configured)
            configured_host = parsed.hostname or ""
        except ValueError:
            return configured
        if is_lan_address(configured_host) and is_lan_address(detected_host) and configured_host != detected_host:
            return replace_url_host(configured, detected_host, default_port=port)
        return configured
    host = bind_host.strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::", "[::]"}:
        host = detected_host
    return f"http://{host}:{port}"


def active_peer_urls(
    static_peers: Iterable[str],
    discovered_peers: Iterable[str],
    *,
    discovery_enabled: bool,
) -> list[str]:
    """Prefer fresh multicast peers; retain static peers only as bootstrap fallback."""
    discovered = list(dict.fromkeys(peer.rstrip("/") for peer in discovered_peers if peer.strip()))
    if discovery_enabled and discovered:
        return discovered
    return list(dict.fromkeys([*(peer.rstrip("/") for peer in static_peers if peer.strip()), *discovered]))


def find_unique_ipv4_host(
    seed_host: str,
    probe: Callable[[str], bool],
    *,
    workers: int = 48,
) -> str | None:
    """Probe a bounded /24 and return a host only when exactly one matches."""
    try:
        seed = ipaddress.ip_address(seed_host)
    except ValueError:
        return None
    if seed.version != 4:
        return None
    candidates = [str(address) for address in ipaddress.ip_network(f"{seed}/24", strict=False).hosts() if address != seed]
    if not candidates:
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(candidates))) as executor:
        matches = [host for host, matched in zip(candidates, executor.map(probe, candidates), strict=True) if matched]
    return matches[0] if len(matches) == 1 else None
