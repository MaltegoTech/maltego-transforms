from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.packaging

REPO_ROOT = Path(__file__).resolve().parents[3]


def _workflow(name: str) -> str:
    return (REPO_ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def _job(workflow: str, name: str, next_name: str | None = None) -> str:
    body = workflow.split(f"  {name}:\n", maxsplit=1)[1]
    if next_name is not None:
        body = body.split(f"  {next_name}:\n", maxsplit=1)[0]
    return body


def test_prepare_release_checks_the_draft_only_with_release_write_access() -> None:
    workflow = _workflow("prepare-release.yml")
    build = _job(workflow, "build-release", "attach-release")
    attach = _job(workflow, "attach-release")

    assert "release-tag:" in workflow
    assert "ref: ${{ inputs.release-tag }}" in workflow
    assert 'NORMALIZED_TAG="${RELEASE_TAG#v}"' in workflow
    assert 'poetry version --short' in workflow
    assert 'gh release view "$RELEASE_TAG" --json isDraft' not in build
    assert 'gh release view "$RELEASE_TAG" --json isDraft' in attach
    assert "must still be a draft" in attach
    assert attach.index("Verify release is still a draft") < attach.index(
        "Attach wheel + sdist + SBOM to the draft release"
    )


def test_prepare_release_workflow_attaches_all_assets_without_publishing() -> None:
    workflow = _workflow("prepare-release.yml")

    assert 'gh release upload "$RELEASE_TAG"' in workflow
    assert "dist/*.whl" in workflow
    assert "dist/*.tar.gz" in workflow
    assert "dist/sbom/maltego-transforms-sbom.cdx.json" in workflow
    assert "gh release edit" not in workflow


def test_prepare_release_separates_read_only_build_from_write_enabled_attachment() -> None:
    workflow = _workflow("prepare-release.yml")
    build = _job(workflow, "build-release", "attach-release")
    attach = _job(workflow, "attach-release")

    assert "contents: write" not in build
    assert "persist-credentials: false" in build
    assert "contents: write" in attach
    assert "actions/download-artifact@v8" in attach
    assert "poetry install" not in attach
    assert "poetry run pytest" not in attach


def test_prepare_release_serializes_and_attests_the_build() -> None:
    workflow = _workflow("prepare-release.yml")
    build = _job(workflow, "build-release", "attach-release")
    attach = _job(workflow, "attach-release")

    assert "group: release-${{ inputs.release-tag }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "attestations: write" in build
    assert "artifact-metadata: write" in build
    assert "id-token: write" in build
    assert "actions/attest@v4" in build
    assert '"$GITHUB_REF" != "refs/heads/main"' in build
    assert '"$(git rev-parse HEAD)" != "$GITHUB_SHA"' in build
    assert "Validate local release asset set" not in attach
    assert "Verify exact draft release assets and digests" not in attach
    assert "actions/setup-python@v7" not in attach


def test_published_release_workflow_downloads_assets_for_pypi_without_uploading_to_release() -> None:
    workflow = _workflow("release.yml")
    publish = _job(workflow, "publish-pypi")

    assert "types: [published]" in workflow
    assert "contents: read" in publish
    assert "GH_REPO: ${{ github.repository }}" in publish
    assert "RELEASE_TAG: ${{ github.event.release.tag_name }}" in publish
    assert 'gh release download "$RELEASE_TAG"' in publish
    assert publish.count("${{ github.event.release.tag_name }}") == 2
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "gh release upload" not in workflow


def test_published_release_requires_immutable_attested_assets() -> None:
    workflow = _workflow("release.yml")
    publish = _job(workflow, "publish-pypi")

    assert "group: release-${{ github.event.release.tag_name }}" in publish
    assert "attestations: read" in publish
    assert "isImmutable" in publish
    assert "Verify immutable release asset set" in publish
    assert "Expected exactly one wheel, one sdist, and one SBOM" in publish
    assert "Validate release asset versions and digests" not in publish
    assert 'asset["digest"]' not in publish
    assert "actions/setup-python@v7" not in publish
    assert 'gh attestation verify "$asset"' in publish
    assert '--source-digest "$GITHUB_SHA"' in publish
    assert "--signer-workflow MaltegoTech/maltego-transforms/.github/workflows/prepare-release.yml" in publish
    assert "pypi.org/pypi/maltego-transforms" not in publish
    assert "Verify existing PyPI files before retry" not in publish
    assert "Verify published PyPI file digests" not in publish
    assert "skip-existing: true" in publish


def test_testpypi_remains_manual_and_does_not_receive_release_write_permission() -> None:
    workflow = _workflow("release.yml")
    build = _job(workflow, "build-testpypi", "publish-testpypi")
    publish = _job(workflow, "publish-testpypi", "publish-pypi")

    assert "github.event_name == 'workflow_dispatch'" in build
    assert "contents: write" not in build
    assert "environment:\n      name: testpypi" in publish
    assert "skip-existing: true" in publish


@pytest.mark.parametrize("name", ["prepare-release.yml", "release.yml"])
def test_release_workflow_yaml_is_valid(name: str) -> None:
    workflow = _workflow(name)

    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed["jobs"], dict)
    assert "python - <<'PY'" not in workflow
