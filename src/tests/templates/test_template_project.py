import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.template


def test_template_project_allows_maltego_app_cors_by_default() -> None:
    project_template = Path("src/maltego/template_dir/project.py").read_text()

    assert "ServerHTTPSettings" in project_template
    assert 'protocol="http"' in project_template
    assert 'cors_allowed_origins=["https://app.maltego.com"]' in project_template
    assert "ssl=False" not in project_template


def test_minimal_template_project_uses_single_http_configuration_source() -> None:
    project_template = Path("src/maltego/template_minimal_dir/project.py").read_text()

    assert "ServerHTTPSettings" in project_template
    assert 'protocol="http"' in project_template
    assert 'cors_allowed_origins=["https://app.maltego.com"]' in project_template
    assert "ssl=False" not in project_template


@pytest.mark.parametrize(
    "readme_path",
    [
        "src/maltego/template_dir/README.md",
        "src/maltego/template_minimal_dir/README.md",
    ],
)
def test_template_readmes_configure_https_via_http_settings(readme_path: str) -> None:
    readme = Path(readme_path).read_text()

    assert 'protocol="https"' in readme
    assert 'cert_key=".local/server.key"' in readme
    assert 'cert_file=".local/server.crt"' in readme
    assert "ssl=True" not in readme


def test_template_project_dependencies_track_current_package_versions() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    sdk_version = pyproject["tool"]["poetry"]["version"]
    requirements = Path("src/maltego/template_dir/requirements.txt").read_text().splitlines()

    assert f"maltego-transforms>={sdk_version}" in requirements
    assert "maltego-transforms-std-entities>=1.0.0" in requirements
