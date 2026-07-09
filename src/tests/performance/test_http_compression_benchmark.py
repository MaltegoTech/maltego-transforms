# Copyright (c) Maltego Technologies GmbH.
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_SCRIPT = REPO_ROOT / "benchmarks" / "http_compression.py"


def _stderr_without_starlette_deprecation(stderr: str) -> str:
    """Drop the benign StarletteDeprecationWarning (httpx/testclient) emitted at
    import time so a genuine error/traceback still fails the test."""
    kept: list[str] = []
    lines = stderr.splitlines()
    i = 0
    while i < len(lines):
        if "StarletteDeprecationWarning" in lines[i]:
            i += 1
            if i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                i += 1  # skip the source-echo line that follows the warning
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept).strip()


def test_http_compression_benchmark_emits_before_after_size_json(
    tmp_path: Path,
) -> None:
    off_output_path = tmp_path / "compression-off.json"
    gzip_output_path = tmp_path / "compression-gzip.json"

    off_result = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--compression",
            "off",
            "--output",
            str(off_output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    gzip_result = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--compression",
            "gzip",
            "--output",
            str(gzip_output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _stderr_without_starlette_deprecation(off_result.stderr) == ""
    assert _stderr_without_starlette_deprecation(gzip_result.stderr) == ""

    off_payload = json.loads(off_output_path.read_text(encoding="utf-8"))
    gzip_payload = json.loads(gzip_output_path.read_text(encoding="utf-8"))

    assert off_payload["compression"] == "off"
    assert gzip_payload["compression"] == "gzip"
    assert {
        "GET /pytest/assets",
        "GET /pytest/transforms",
        "POST /pytest/transforms/{transform_id}/run",
    } == {item["endpoint"] for item in off_payload["results"]}
    assert {
        "GET /pytest/assets",
        "GET /pytest/transforms",
        "POST /pytest/transforms/{transform_id}/run",
    } == {item["endpoint"] for item in gzip_payload["results"]}

    off_by_endpoint = {item["endpoint"]: item for item in off_payload["results"]}
    gzip_by_endpoint = {item["endpoint"]: item for item in gzip_payload["results"]}

    assert all(item["content_encoding"] is None for item in off_payload["results"])
    assert all(
        item["wire_bytes_source"] == "content-length"
        for item in off_payload["results"]
    )
    assert all(
        item["wire_bytes_source"] == "content-length"
        for item in gzip_payload["results"]
    )
    assert all(item["required_headers_present"] for item in off_payload["results"])
    assert all(item["required_headers_present"] for item in gzip_payload["results"])

    compressed_items = [
        item for item in gzip_payload["results"] if item["content_encoding"] == "gzip"
    ]
    assert compressed_items
    assert any(item["ratio"] < 1 for item in compressed_items)

    for endpoint, off_item in off_by_endpoint.items():
        gzip_item = gzip_by_endpoint[endpoint]
        assert gzip_item["plain_bytes"] == off_item["plain_bytes"]
        assert off_item["wire_bytes"] == off_item["plain_bytes"]
