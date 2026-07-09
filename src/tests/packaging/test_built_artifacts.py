import subprocess
import tarfile
import zipfile
from pathlib import Path
from email.parser import Parser

import pytest

pytestmark = pytest.mark.packaging


def build_artifacts(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["poetry", "build", "--output", str(dist_dir)],
        check=True,
        text=True,
        capture_output=True,
    )
    return dist_dir


def wheel_entries(wheel_path: Path) -> set[str]:
    with zipfile.ZipFile(wheel_path) as archive:
        return set(archive.namelist())


def sdist_entries(sdist_path: Path) -> set[str]:
    with tarfile.open(sdist_path) as archive:
        return set(archive.getnames())


def assert_no_public_artifact_forbidden_entries(entries: set[str]) -> None:
    forbidden_fragments = [
        "maltego_trx",
        "maltego/server/v2",
        "maltego/server/trx",
        "src/tests/example",
        ".env",
        "server.key",
        "server.crt",
        "_private.pem",
    ]
    for fragment in forbidden_fragments:
        assert not any(fragment in entry for entry in entries), fragment


SDK_INTERNAL_TERMS = [
    "-".join(["maltego", "connectors", "python"]),
    "1" + "Password",
    " ".join(["Azure", "DevOps", "feed"]),
    "op" + "://",
]


def wheel_text_payloads(wheel_path: Path) -> dict[str, str]:
    payloads: dict[str, str] = {}
    with zipfile.ZipFile(wheel_path) as archive:
        for name in archive.namelist():
            if name.endswith((".py", ".md", ".txt", ".rst", ".toml", ".yml", ".yaml")):
                payloads[name] = archive.read(name).decode("utf-8", errors="replace")
    return payloads


def sdist_text_payloads(sdist_path: Path) -> dict[str, str]:
    payloads: dict[str, str] = {}
    with tarfile.open(sdist_path) as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.endswith((".py", ".md", ".txt", ".rst", ".toml", ".yml", ".yaml")):
                extracted = archive.extractfile(member)
                assert extracted is not None
                payloads[member.name] = extracted.read().decode("utf-8", errors="replace")
    return payloads


def assert_no_internal_terms_in_payloads(payloads: dict[str, str]) -> None:
    hits = {
        path: term
        for path, text in payloads.items()
        for term in SDK_INTERNAL_TERMS
        if term in text
    }
    assert hits == {}


def read_wheel_metadata(wheel_path: Path) -> str:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        return archive.read(metadata_name).decode("utf-8")


def test_built_wheel_excludes_private_and_classic_material(tmp_path: Path) -> None:
    dist_dir = build_artifacts(tmp_path)
    wheel_path = next(dist_dir.glob("*.whl"))

    assert_no_public_artifact_forbidden_entries(wheel_entries(wheel_path))


def test_built_sdist_excludes_private_and_classic_material(tmp_path: Path) -> None:
    dist_dir = build_artifacts(tmp_path)
    sdist_path = next(dist_dir.glob("*.tar.gz"))

    assert_no_public_artifact_forbidden_entries(sdist_entries(sdist_path))


def test_built_wheel_requires_python_matches_support_policy(tmp_path: Path) -> None:
    # Python 3.14 is supported (PEP 649 annotation handling and the pydantic 2.13
    # bump are validated under 3.14); 3.15 is the next excluded major.
    dist_dir = build_artifacts(tmp_path)
    wheel_path = next(dist_dir.glob("*.whl"))
    metadata = Parser().parsestr(read_wheel_metadata(wheel_path))

    assert metadata["Requires-Python"] == ">=3.10,<3.15"


def test_built_wheel_contains_no_internal_terms(tmp_path: Path) -> None:
    dist_dir = build_artifacts(tmp_path)
    wheel_path = next(dist_dir.glob("*.whl"))

    assert_no_internal_terms_in_payloads(wheel_text_payloads(wheel_path))


def test_built_sdist_contains_no_internal_terms(tmp_path: Path) -> None:
    dist_dir = build_artifacts(tmp_path)
    sdist_path = next(dist_dir.glob("*.tar.gz"))

    assert_no_internal_terms_in_payloads(sdist_text_payloads(sdist_path))
