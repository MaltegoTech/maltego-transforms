import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "resources" / "generate_sbom.py"
spec = importlib.util.spec_from_file_location("generate_sbom", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
generate_sbom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_sbom)


def resolve_output_path(output: str | None) -> Path:
    resolver = getattr(generate_sbom, "resolve_output_path", None)
    if resolver is None:
        pytest.fail("resolve_output_path is not implemented")
    return resolver(output)


def find_cyclonedx_binary() -> str | None:
    finder = getattr(generate_sbom, "find_cyclonedx_binary", None)
    if finder is None:
        pytest.fail("find_cyclonedx_binary is not implemented")
    return finder()


def test_resolve_output_path_defaults_to_dist_release_sbom() -> None:
    assert resolve_output_path(None) == Path("dist/maltego-transforms-sbom.cdx.json")


def test_resolve_output_path_allows_relative_dist_file() -> None:
    assert resolve_output_path("dist/custom-sbom.cdx.json") == Path("dist/custom-sbom.cdx.json")


@pytest.mark.parametrize("output", ["../sbom.json", "dist/../sbom.json"])
def test_resolve_output_path_rejects_paths_outside_dist(output: str) -> None:
    with pytest.raises(ValueError, match="dist"):
        resolve_output_path(output)


def test_resolve_output_path_rejects_absolute_paths(tmp_path) -> None:
    with pytest.raises(ValueError, match="relative"):
        resolve_output_path(str(tmp_path / "sbom.json"))


def test_find_cyclonedx_binary_accepts_current_and_legacy_entrypoints(monkeypatch) -> None:
    calls = []

    def fake_which(binary: str) -> str | None:
        calls.append(binary)
        if binary == "cyclonedx-bom":
            return "/usr/local/bin/cyclonedx-bom"
        return None

    monkeypatch.setattr(generate_sbom.shutil, "which", fake_which)

    assert find_cyclonedx_binary() == "/usr/local/bin/cyclonedx-bom"
    assert calls == ["cyclonedx-py", "cyclonedx-bom"]
