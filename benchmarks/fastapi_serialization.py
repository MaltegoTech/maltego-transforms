#!/usr/bin/env python
# Copyright (c) Maltego Technologies GmbH.

import argparse
import json
import platform
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fastapi
import pydantic
import starlette
from starlette.testclient import TestClient

from maltego.model.entity import MEF, MaltegoEntity, MaltegoEntityConfig
from maltego.server import MaltegoServerSettings, MaltegoTransformServer

NAMESPACE = "maltoso.test"
PREFIX = "pytest"
TRANSFORM_ID = f"{NAMESPACE}.Test"
HEADERS = {"Maltego-API-Key": "foobarbaz"}
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


def build_server() -> MaltegoTransformServer:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix=PREFIX,
        full_host_url="https://maltoso.com/",
    )
    server = MaltegoTransformServer(settings=settings)

    @server.register_transform(
        display_name="Test",
        name="Test",
        description="test",
        transform_set="pytest",
    )
    async def benchmark_transform(
        input_entity: BenchmarkPhrase,
        settings: dict[str, Any],
    ) -> BenchmarkPhrase:
        return BenchmarkPhrase("Test")

    server.register_entity(BenchmarkPhrase)
    server.setup(settings)
    server.runner.startup()
    return server


def measure_endpoint(
    endpoint: str,
    iterations: int,
    call: Callable[[], Any],
) -> dict[str, Any]:
    durations = []
    payload_bytes = 0
    content_type = ""
    for _ in range(iterations):
        start = time.perf_counter()
        response = call()
        elapsed = time.perf_counter() - start
        response.raise_for_status()
        durations.append(elapsed)
        payload_bytes = len(response.content)
        content_type = response.headers.get("content-type", "")

    total_seconds = sum(durations)
    return {
        "endpoint": endpoint,
        "iterations": iterations,
        "total_seconds": total_seconds,
        "requests_per_second": iterations / total_seconds if total_seconds else 0,
        "median_ms": statistics.median(durations) * 1000,
        "payload_bytes": payload_bytes,
        "content_type": content_type,
    }


def run_benchmark(iterations: int) -> dict[str, Any]:
    server = build_server()
    client = TestClient(server.app)
    try:
        seed = client.post(
            f"/{PREFIX}/transforms/{TRANSFORM_ID}/run",
            json=RUN_REQUEST,
            headers=dict(HEADERS),
        )
        seed.raise_for_status()
        run_id = seed.json()["result"]["runId"]

        results = [
            measure_endpoint(
                "GET /pytest/assets",
                iterations,
                lambda: client.get(f"/{PREFIX}/assets", headers=dict(HEADERS)),
            ),
            measure_endpoint(
                "GET /pytest/transforms",
                iterations,
                lambda: client.get(f"/{PREFIX}/transforms", headers=dict(HEADERS)),
            ),
            measure_endpoint(
                "POST /pytest/transforms/{transform_id}/run",
                iterations,
                lambda: client.post(
                    f"/{PREFIX}/transforms/{TRANSFORM_ID}/run",
                    json=RUN_REQUEST,
                    headers=dict(HEADERS),
                ),
            ),
            measure_endpoint(
                "GET /pytest/transforms/{transform_id}/run/{run_id}/results",
                iterations,
                lambda: client.get(
                    f"/{PREFIX}/transforms/{TRANSFORM_ID}/run/{run_id}/results",
                    headers=dict(HEADERS),
                ),
            ),
        ]
    finally:
        server.runner.shutdown()

    return {
        "benchmark": "fastapi_serialization",
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "pydantic": pydantic.__version__,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark local FastAPI serialization for representative SDK v3 JSON endpoints."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=200,
        help="Number of requests to send to each endpoint.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the benchmark JSON output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations <= 0:
        raise SystemExit("--iterations must be greater than zero")

    payload = run_benchmark(args.iterations)
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
