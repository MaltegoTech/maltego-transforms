from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import toml as tomllib


pytestmark = pytest.mark.packaging

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_dev_dependencies_include_commit_message_tooling() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = pyproject["tool"]["poetry"]["group"]["dev"]["dependencies"]

    assert "pre-commit" in dev_dependencies
    assert "commitizen" in dev_dependencies


def test_pre_commit_config_checks_conventional_commit_messages() -> None:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "poetry run cz check --commit-msg-file" in config
    assert "stages: [commit-msg]" in config


def test_contributing_documents_conventional_commit_hook_setup() -> None:
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "Conventional Commits" in contributing
    assert "https://www.conventionalcommits.org/" in contributing
    assert "pre-commit install --hook-type commit-msg" in contributing
