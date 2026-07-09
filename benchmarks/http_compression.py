#!/usr/bin/env python
# Copyright (c) Maltego Technologies GmbH.

import argparse
import json
import platform
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import fastapi
import pydantic
import starlette
from starlette.testclient import TestClient

from maltego.model.entity import MEF, MaltegoEntity, MaltegoEntityConfig
from maltego.model.server import ServerHTTPSettings
from maltego.server import MaltegoServerSettings, MaltegoTransformServer

CompressionMode = Literal["off", "gzip"]

NAMESPACE = "maltoso.test"
PREFIX = "pytest"
HEADERS = {
    "Accept-Encoding": "gzip",
    "Maltego-API-Key": "foobarbaz",
}
RUN_REQUEST = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}


class BenchmarkPhrase(MaltegoEntity):
    TYPE_NAME = "maltego.Phrase"
    Config = MaltegoEntityConfig(
        value_property="text",
        display_name="Phrase",
        description="Any text or part thereof",
        display_property="text",
        category="Personal",
        display_name_plural="Phrases",
        icon_resource="Phrase",
        _visible=True,
    )
    text: str = MEF(
        name="text",
        display_name="Text",
        sample_value="Some phrase",
    )


def build_server(compression: CompressionMode) -> MaltegoTransformServer:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix=PREFIX,
        full_host_url="https://maltoso.com/",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=compression == "gzip",
            http_response_compression_minimum_size=500,
        ),
    )
    server = MaltegoTransformServer(settings=settings)

    for index in range(30):

        @server.register_transform(
            display_name=f"Compression Benchmark {index}",
            name=f"CompressionBenchmark{index}",
            description=(
                "Compression benchmark transform with repeated JSON metadata. "
                "This intentionally creates a representative discovery payload."
            ),
            transform_set="pytest",
        )
        async def benchmark_transform(
            input_entity: BenchmarkPhrase,
            settings: dict[str, Any],
        ) -> BenchmarkPhrase:
            del input_entity, settings
            return BenchmarkPhrase("Test")

    server.register_entity(BenchmarkPhrase)
    server.setup(settings)
    server.runner.startup()
    return server


def _wire_bytes(response: Any) -> tuple[int, str]:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        return int(content_length), "content-length"
    if response.headers.get("content-encoding") == "gzip":
        return len(response.content), "decoded-body-fallback"
    return len(response.content), "body"


def _required_headers(endpoint: str) -> list[str]:
    if endpoint.startswith("POST "):
        return ["maltego-protocol-version", "maltego-run-state"]
    return [
        "maltego-protocol-version",
        "vary",
        "maltego-transform-supported-oauth-formats",
    ]


def measure_endpoint(
    endpoint: str,
    call: Callable[[], Any],
) -> dict[str, Any]:
    response = call()
    response.raise_for_status()
    plain_bytes = len(response.content)
    wire_bytes, wire_bytes_source = _wire_bytes(response)
    required_headers = _required_headers(endpoint)
    headers_present = {
        header: response.headers.get(header) is not None for header in required_headers
    }
    return {
        "endpoint": endpoint,
        "status_code": response.status_code,
        "content_encoding": response.headers.get("content-encoding"),
        "content_length": response.headers.get("content-length"),
        "plain_bytes": plain_bytes,
        "wire_bytes": wire_bytes,
        "wire_bytes_source": wire_bytes_source,
        "ratio": wire_bytes / plain_bytes if plain_bytes else None,
        "required_headers_present": all(headers_present.values()),
        "headers_present": headers_present,
        "vary": response.headers.get("vary"),
    }


def run_benchmark(compression: CompressionMode) -> dict[str, Any]:
    server = build_server(compression)
    client = TestClient(server.app)
    transform_id = f"{NAMESPACE}.CompressionBenchmark0"
    try:
        results = [
            measure_endpoint(
                "GET /pytest/assets",
                lambda: client.get(f"/{PREFIX}/assets", headers=dict(HEADERS)),
            ),
            measure_endpoint(
                "GET /pytest/transforms",
                lambda: client.get(f"/{PREFIX}/transforms", headers=dict(HEADERS)),
            ),
            measure_endpoint(
                "POST /pytest/transforms/{transform_id}/run",
                lambda: client.post(
                    f"/{PREFIX}/transforms/{transform_id}/run",
                    json=RUN_REQUEST,
                    headers=dict(HEADERS),
                ),
            ),
        ]
    finally:
        server.runner.shutdown()

    return {
        "benchmark": "http_compression",
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "compression": compression,
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "pydantic": pydantic.__version__,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure local SDK v3 JSON response sizes with optional gzip compression."
    )
    parser.add_argument(
        "--compression",
        choices=["off", "gzip"],
        default="off",
        help="Compression mode to configure on the local test server.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the benchmark JSON output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_benchmark(args.compression)
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
