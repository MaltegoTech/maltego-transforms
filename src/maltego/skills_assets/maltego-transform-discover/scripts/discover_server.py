"""
discover_server.py — Query a running maltego-transforms SDK server's discovery endpoints.

Usage:
    python discover_server.py [--host HOST] [--port PORT] [--api-prefix PREFIX]
    python discover_server.py --host 127.0.0.1 --port 8080

Outputs JSON to stdout. Exits non-zero if the server is unreachable or returns an error.

This script never imports or executes customer transform code — it queries the live server API only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def _get_json(url: str) -> object:
    # Only ever fetch over http(s). urllib also supports file:// and other
    # schemes, so guard the (CLI-supplied) URL before opening it.
    if urlparse(url).scheme not in ("http", "https"):
        print(f"ERROR: refusing to fetch non-http(s) URL: {url}", file=sys.stderr)
        sys.exit(2)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"ERROR: Could not reach {url} — {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON from {url} — {e}", file=sys.stderr)
        sys.exit(1)


def _normalise_api_prefix(api_prefix: str) -> str:
    prefix = api_prefix.strip("/")
    if not prefix:
        return "api/v3"
    if prefix.endswith("api/v3"):
        return prefix
    return f"{prefix}/api/v3"


def discover(host: str, port: int, api_prefix: str = "api/v3") -> dict:
    base = f"http://{host}:{port}"
    discovery_base = f"{base}/{_normalise_api_prefix(api_prefix)}"

    transforms = _get_json(f"{discovery_base}/transforms")
    entities = _get_json(f"{discovery_base}/assets/entities")

    try:
        health = _get_json(f"{base}/health")
    except SystemExit:
        health = None  # /health is optional

    return {
        "server": f"{host}:{port}",
        "transforms": transforms,
        "entities": entities,
        "health": health,
    }


def main():
    parser = argparse.ArgumentParser(description="Discover transforms and entities from a running SDK server.")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument(
        "--api-prefix",
        default="api/v3",
        help="SDK API prefix, or the custom MaltegoServerSettings.api_prefix value (default: api/v3)",
    )
    parser.add_argument("--transforms-only", action="store_true", help="Only print transforms list")
    parser.add_argument("--entities-only", action="store_true", help="Only print entities list")
    args = parser.parse_args()

    result = discover(args.host, args.port, api_prefix=args.api_prefix)

    if args.transforms_only:
        print(json.dumps(result["transforms"], indent=2))
    elif args.entities_only:
        print(json.dumps(result["entities"], indent=2))
    else:
        print(json.dumps(result, indent=2))

    t_count = len(result["transforms"]) if isinstance(result["transforms"], list) else "?"
    e_count = len(result["entities"]) if isinstance(result["entities"], list) else "?"
    print(f"\nServer {result['server']}: {t_count} transforms, {e_count} entity types", file=sys.stderr)


if __name__ == "__main__":
    main()
