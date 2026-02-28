"""
Lockdown Middleware - Restricts access to the security agent to internal network only.

Three layers of protection:
1. IP Whitelist - Only accepts requests from known internal IP ranges
   (Docker networks, localhost, private RFC1918 ranges)
2. API Key Authentication - Requires X-Internal-Key header for all
   non-health endpoints
3. Host binding - Agent binds to 0.0.0.0 but the middleware rejects
   any request from outside the allowed IP ranges

This ensures the security agent cannot be tampered with, disabled,
or probed by external attackers.
"""

import ipaddress
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Endpoints that are always accessible (no auth needed)
PUBLIC_ENDPOINTS = {"/health", "/metrics"}

# Endpoints that need full lockdown (API key + IP whitelist)
# Everything else besides PUBLIC_ENDPOINTS is locked down


def parse_allowed_networks(allowed_ips_str: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse comma-separated IP/CIDR list into network objects."""
    networks = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            # Try as network (e.g., 10.0.0.0/8)
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            try:
                # Try as single address (e.g., 127.0.0.1)
                addr = ipaddress.ip_address(entry)
                if isinstance(addr, ipaddress.IPv4Address):
                    networks.append(ipaddress.ip_network(f"{entry}/32"))
                else:
                    networks.append(ipaddress.ip_network(f"{entry}/128"))
            except ValueError:
                logger.warning(f"Invalid IP/CIDR in ALLOWED_IPS: '{entry}', skipping")
    return networks


def is_ip_allowed(client_ip: str, allowed_networks: list) -> bool:
    """Check if a client IP is within any allowed network range."""
    try:
        addr = ipaddress.ip_address(client_ip)
        # Handle IPv4-mapped IPv6 (e.g., ::ffff:127.0.0.1)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        return any(addr in network for network in allowed_networks)
    except ValueError:
        return False


class LockdownState:
    """Holds parsed lockdown configuration."""

    def __init__(self, enabled: bool, api_key: str, allowed_ips_str: str):
        self.enabled = enabled
        self.api_key = api_key
        self.allowed_networks = parse_allowed_networks(allowed_ips_str)
        self.key_required = bool(api_key)

        if enabled:
            logger.info(
                f"Lockdown ENABLED: {len(self.allowed_networks)} allowed networks, "
                f"API key required: {self.key_required}"
            )
        else:
            logger.warning("Lockdown DISABLED: security agent is accessible from any IP")


# Module-level state, initialized from main.py
_lockdown: LockdownState | None = None


def init_lockdown(enabled: bool, api_key: str, allowed_ips_str: str):
    """Initialize lockdown configuration. Called once at startup."""
    global _lockdown
    _lockdown = LockdownState(enabled, api_key, allowed_ips_str)


async def lockdown_middleware(request: Request, call_next):
    """
    FastAPI middleware that enforces internal-only access.

    - Public endpoints (/health, /metrics) are always allowed
    - All other endpoints require:
      1. Client IP in the allowed IP ranges
      2. Valid X-Internal-Key header (if INTERNAL_API_KEY is configured)
    """
    if _lockdown is None or not _lockdown.enabled:
        return await call_next(request)

    path = request.url.path

    # Public endpoints are always accessible
    if path in PUBLIC_ENDPOINTS:
        return await call_next(request)

    # Also allow /metrics sub-paths (Prometheus)
    if path.startswith("/metrics"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"

    # Layer 1: IP whitelist
    if not is_ip_allowed(client_ip, _lockdown.allowed_networks):
        logger.warning(f"LOCKDOWN: Rejected request from external IP {client_ip} to {path}")
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Access denied. This service is restricted to internal network only.",
            },
        )

    # Layer 2: API key (if configured)
    if _lockdown.key_required:
        provided_key = request.headers.get("X-Internal-Key", "")
        if provided_key != _lockdown.api_key:
            logger.warning(f"LOCKDOWN: Invalid API key from {client_ip} to {path}")
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or missing X-Internal-Key header.",
                },
            )

    return await call_next(request)
