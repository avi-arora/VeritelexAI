"""SSRF-safe URL resolution for citation verification.

URLs come from model output and search results, so they are untrusted:
only http(s) on default ports, every hop's host must resolve exclusively to
public addresses, redirects are followed manually (max 5) and re-checked,
and bodies are never downloaded beyond the response headers.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 5
_UA = "VeriteLexAI-citation-check/1.0"


async def _host_is_public(host: str) -> bool:
    # TODO(security): DNS-rebinding TOCTOU — httpx re-resolves the host after this check.
    # Mitigated by only issuing body-less GETs to model-provided URLs and running on Cloud Run
    # (no metadata-reachable internal services besides the metadata server, which needs a header);
    # pin the resolved IP via a custom transport before any wider use.
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


def _acceptable(url: str) -> bool:
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return False
    return p.port in (None, 80, 443)


async def resolve_url(url: str, client: httpx.AsyncClient) -> tuple[str | None, int | None]:
    """Follow redirects safely. Returns (final_url, status) or (None, None) if unreachable/blocked."""
    current = url.strip()
    for _ in range(MAX_REDIRECTS + 1):
        if not _acceptable(current) or not await _host_is_public(urlsplit(current).hostname or ""):
            return None, None
        try:
            async with client.stream("GET", current, headers={"User-Agent": _UA}) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    current = urljoin(current, resp.headers["location"])
                    continue
                return str(resp.url), resp.status_code
        except (httpx.HTTPError, ValueError):
            return None, None
    return None, None


def make_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=False, timeout=timeout, limits=httpx.Limits(max_connections=10))


def canon(url: str) -> str:
    p = urlsplit(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}".lower()


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")
