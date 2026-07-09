from pathlib import Path

import tomllib


def test_tracing_extra_installs_otlp_grpc_exporter_used_by_docs():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    tracing_extra = pyproject["tool"]["poetry"]["extras"]["tracing"]

    assert "opentelemetry-exporter-otlp-proto-grpc" in dependencies
    assert "opentelemetry-exporter-otlp-proto-grpc" in tracing_extra
