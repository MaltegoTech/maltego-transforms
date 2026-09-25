# Copyright (c) Maltego Technologies GmbH.
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_SCRIPT = REPO_ROOT / "benchmarks" / "fastapi_serialization.py"


_BENIGN_DEPRECATIONS = ("StarletteDeprecationWarning", "AuthlibDeprecationWarning")
_MAX_CONTINUATION_LINES = 3  # bound how much unindented text we treat as part of one warning
_FAILURE_MARKERS = ("Traceback (most recent call last)", "Error", "Exception")


def _stderr_without_starlette_deprecation(stderr: str) -> str:
    """Drop benign deprecation warnings (httpx/testclient, authlib.jose) emitted at
    import time so a genuine error/traceback still fails the test."""
    kept: list[str] = []
    lines = stderr.splitlines()
    i = 0
    while i < len(lines):
        if any(marker in lines[i] for marker in _BENIGN_DEPRECATIONS):
            i += 1
            # skip any further message-continuation lines (unindented), capped
            # so unrelated real output can't be silently absorbed
            skipped = 0
            while (
                i < len(lines)
                and lines[i]
                and not lines[i][0].isspace()
                and skipped < _MAX_CONTINUATION_LINES
                and not any(marker in lines[i] for marker in _FAILURE_MARKERS)
            ):
                i += 1
                skipped += 1
            if i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                i += 1  # skip the source-echo line that follows the warning
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept).strip()


def test_stderr_filter_keeps_failure_after_deprecation_warning() -> None:
    stderr = "StarletteDeprecationWarning: benign\nRuntimeError: benchmark failed"

    assert _stderr_without_starlette_deprecation(stderr) == "RuntimeError: benchmark failed"


def test_fastapi_serialization_benchmark_emits_required_json(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"

    result = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--iterations",
            "1",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _stderr_without_starlette_deprecation(result.stderr) == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["fastapi"]
    assert payload["starlette"]
    assert payload["pydantic"]
    assert {
        "GET /pytest/assets",
        "GET /pytest/transforms",
        "POST /pytest/transforms/{transform_id}/run",
        "GET /pytest/transforms/{transform_id}/run/{run_id}/results",
    } == {item["endpoint"] for item in payload["results"]}

    for item in payload["results"]:
        assert item["iterations"] == 1
        assert item["total_seconds"] >= 0
        assert item["requests_per_second"] >= 0
        assert item["median_ms"] >= 0
        assert item["payload_bytes"] > 0
        assert item["content_type"].startswith("application/json")
