"""SSRF guards for outbound HTTP (Phase P1)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}
_ALLOWED_SCHEMES = {"http", "https"}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fe80::/10"))
        or (ip.version == 4 and str(ip).startswith("0."))
    )


def assert_safe_outbound_url(url: str) -> str:
    """
    Validate URL for server-side fetch/POST. Raises ValueError if unsafe.

    Blocks: non-http(s), file://, link-local, loopback, private, metadata IPs.
    Resolves DNS and checks all returned addresses.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL is empty")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        raise ValueError(f"scheme '{scheme}' is not allowed")
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("only http and https URLs are allowed")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL host is missing")
    if host in {"localhost", "metadata.google.internal", "metadata"}:
        raise ValueError("blocked host")
    # Literal IP in URL
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            raise ValueError("blocked IP address")
        return raw
    except ValueError as exc:
        if "blocked" in str(exc):
            raise
        # Not a literal IP — resolve
        pass

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc
    if not infos:
        raise ValueError("DNS resolution returned no addresses")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise ValueError(f"blocked resolved address {addr}")
    return raw
