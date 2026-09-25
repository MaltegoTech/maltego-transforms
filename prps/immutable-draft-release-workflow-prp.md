## Goal

Make GitHub's UI-led release flow reliably compatible with immutable releases.

## Why

GitHub locks assets when a release is published. The workflow must therefore
prepare and verify an existing UI draft before publication, then publish the
same already-attached package distributions to PyPI after publication.

## Scope

- Add a manual **Prepare Release** workflow for an existing draft selected by
  an explicit tag.
- Change the published-release workflow to publish already-attached artifacts
  to PyPI only.
- Add focused workflow-contract tests.
- Widen supported dependency ranges, regenerate the Poetry lockfile, and adapt
  HTTPX client construction to its current proxy and ASGI transport APIs.
- Configure lockfile-only Python dependency updates through Dependabot.

## Non-goals

- No package version, changelog, tag, ruleset, release, or PyPI publication
  change.
- No intentional SDK behavior change outside the HTTPX compatibility work
  required by the dependency updates.
- No automatic release publication; the human retains the UI publish step.

## Design

`workflow_dispatch` accepts a `release-tag` input. A read-only job checks out
that tag, validates its normalized package version, then tests and builds the
package and SBOM. A separate, write-enabled job confirms the matching GitHub
release is still a draft immediately before attaching those three assets while
leaving the draft unpublished. GitHub attestations bind the artifacts to the
preparation workflow and tagged main commit.

The release-published path requires an immutable release containing one wheel,
one sdist, and one SBOM, then verifies their attestations before publishing the
wheel and sdist to PyPI. TestPyPI remains an explicit manual path and does not
interact with GitHub releases.

## Files

- CREATE `.github/workflows/prepare-release.yml`: prepare and verify an existing
  draft release.
- MODIFY `.github/workflows/release.yml`: publish verified immutable assets.
- CREATE `src/tests/packaging/test_release_workflows.py`: static workflow
  contract tests, written first.

## Test matrix

- Workflow exposes an explicit release-tag preparation input.
- Draft preparation checks out the requested tag, validates normalized package
  version, and uploads all three assets only after the release-write job
  confirms the release is still a draft.
- Preparation separates read-only build work from release-write access and
  attests the build outputs.
- Published-release PyPI publishing requires the expected immutable assets and
  verifies their provenance before publication.
- Existing TestPyPI manual behavior remains explicit.

## Verification

```bash
poetry run pytest src/tests/packaging/test_release_workflows.py -q
poetry run ruff check src/tests/packaging/test_release_workflows.py
poetry run pytest src/tests -q
git diff --check
```

## Definition of done

- [x] Tests were observed failing before workflow implementation.
- [x] The draft preparation path cannot publish a release.
- [x] The published-release path cannot modify release assets.
- [x] Package version and release tag are compared with an optional `v` prefix.
- [x] Dependency ranges, lockfile, Dependabot coverage, and HTTPX compatibility
  updates are consistent.
