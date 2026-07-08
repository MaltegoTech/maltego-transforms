import ipaddress
import json
from typing import Optional

import fastapi

from maltego.model.server import MaltegoServerSettings
from maltego.model.types import ExecutionState

MALTEGO_PROTOCOL_VERSION_3_1 = "3.1"
MALTEGO_PROTOCOL_VERSION_3_2 = "3.2"
DEFAULT_PROTOCOL_VERSION = MALTEGO_PROTOCOL_VERSION_3_1

# in case the discovery results get cached, we should return Vary headers
# to ensure the cache is invalidated when the client capabilities change
VARY_HEADERS_LIST = [
    "Maltego-Client-Capabilities",
    "Maltego-Protocol-Version",
    "Maltego-Client-Identifier",
    "Maltego-Client-Version",
    "User-Agent",
]
VARY_HEADERS = ", ".join(VARY_HEADERS_LIST)

def set_state_header(state: ExecutionState, response: fastapi.Response | fastapi.HTTPException) -> None:
    """Helper function to set the transform run state in response headers."""
    response.headers["maltego-run-state"] = state.value


def set_run_duration_header(duration_ms: int, response: fastapi.Response) -> None:
    """Set the maltego-run-duration header in the response."""
    response.headers["maltego-run-duration"] = str(duration_ms)


def set_entities_added_header(entities_added: dict, response) -> None:
    """Set the maltego-entities-added header in the response."""
    response.headers["maltego-entities-added"] = json.dumps(entities_added)


def set_protocol_version_header(
        response: fastapi.Response,
        maltego_protocol_version: Optional[str] = None
) -> None:
    """Set the Maltego protocol version header in the response."""
    response.headers["maltego-protocol-version"] = maltego_protocol_version or DEFAULT_PROTOCOL_VERSION


def set_vary_headers(response: fastapi.Response) -> None:
    """
    Set the standard Vary header for Maltego API responses.
    """
    response.headers["Vary"] = ", ".join(VARY_HEADERS_LIST)


def is_forwarded_client_allowed(client_host: Optional[str], forwarded_allow_ips: str) -> bool:
    """Return True if client_host is in the trusted forwarded-proxy allow-list.

    This is a shared utility used by both the server middleware (server/__init__.py)
    and the auth rate-limit key builder (auth/dependency.py) so neither has to
    re-implement the CIDR/IP matching logic.  The function lives here (server/util.py)
    because it has no auth imports, avoiding a circular dependency.
    """
    if not client_host:
        return False
    allowed_hosts = [host.strip() for host in forwarded_allow_ips.split(",")]
    if "*" in allowed_hosts:
        return True
    for allowed_host in allowed_hosts:
        if not allowed_host:
            continue
        try:
            if "/" in allowed_host:
                if ipaddress.ip_address(client_host) in ipaddress.ip_network(
                    allowed_host, strict=False
                ):
                    return True
            elif ipaddress.ip_address(client_host) == ipaddress.ip_address(allowed_host):
                return True
        except ValueError:
            if client_host == allowed_host:
                return True
    return False


def get_supported_protocol_version(client_version: Optional[str], settings: MaltegoServerSettings) -> str:
    """Determines the best protocol version to use based on client request and server settings."""

    del settings

    server_protocol_version = DEFAULT_PROTOCOL_VERSION
    if client_version == MALTEGO_PROTOCOL_VERSION_3_1:
        server_protocol_version = MALTEGO_PROTOCOL_VERSION_3_1
    if client_version == MALTEGO_PROTOCOL_VERSION_3_2:
        server_protocol_version = MALTEGO_PROTOCOL_VERSION_3_2

    return server_protocol_version
