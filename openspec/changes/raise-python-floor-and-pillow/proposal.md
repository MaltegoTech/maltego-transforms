## Why

Three version settings in this repository have fallen behind, and one of them
blocks a security fix:

- **Python 3.10 reached end of life on 2026-10-01** and no longer receives
  security fixes from the Python project. The SDK still declares support for
  it.
- **Pillow 12.3.0 is affected by advisories that are fixed only in Pillow
  13.0.0.** GitHub reports nine of them for this repository:
  GHSA-8g5g-8vmr-9782 (critical), GHSA-58r4-6rv3-gfh8, GHSA-65qm-jvmh-6pqg,
  GHSA-q45j-58j2-45rg, GHSA-pchr-8j38-3x4p, GHSA-p4wg-p73j-c528,
  GHSA-c6hw-5grf-ff96 (high), GHSA-vx6w-vv9f-6gvg and GHSA-462x-pgg6-55fp
  (medium). Pillow's 13.0.0 release notes list more. Two settings block the
  upgrade: the `Pillow = "^12.3.0"` requirement excludes 13, and Pillow 13
  requires Python 3.11 or newer while the SDK still accepts 3.10. Automated
  lockfile-only security updates can change neither.
- **The CI and release workflows run on Python 3.11.** Most installations of
  the SDK run on Python 3.12: it accounts for roughly four in five downloads
  in the 30 days before this change, according to public PyPI download
  statistics. Building and testing releases on 3.12 tests what most users run.

Raising the supported floor to 3.11 unblocks the Pillow upgrade. Moving the
workflows to 3.12 is part of the same version tidy-up.

## Scope and non-goals

Each change and its reason:

| # | Change | Where | Why |
| --- | --- | --- | --- |
| 1 | Supported Python becomes `>=3.11,<3.15` and the 3.10 classifier is removed | `pyproject.toml` | 3.10 is end of life, and Pillow 13 needs 3.11 |
| 2 | Generated `poetry` and `uv` projects declare `requires-python = ">=3.11"` | `src/maltego/_cli.py` | A generated project must not allow a Python the SDK no longer supports |
| 3 | Documentation states Python 3.11–3.14 | `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, both template READMEs, shipped skill compatibility notes, `openspec/config.yaml` | Keep every published statement consistent with the package metadata |
| 4 | Remove the Python 3.10 check in `is_any_union_type` | `src/maltego/util/typing.py` | It is always true on 3.11 and newer |
| 5 | CI, Prepare Release and the Release build job run on Python 3.12 | `.github/workflows/ci.yml`, `prepare-release.yml`, `release.yml` | Build and test on the interpreter most users run |
| 6 | Pillow requirement becomes `>=13.0.0,<14` and the lock moves to 13.0.0 | `pyproject.toml`, `poetry.lock` | Fixes the advisories above |
| 7 | Remove the `types-Pillow` development dependency | `pyproject.toml`, `poetry.lock` | Pillow 13 ships its own type information; the old stubs describe Pillow 10 and would override it for type checkers |
| 8 | Changelog entries | `CHANGELOG.md` | User-facing change |

Non-goals:

- No change to the SDK's Python API, wire protocol, discovery output or
  generated-project layout beyond the `requires-python` line.
- No multi-version test matrix; CI keeps one interpreter.
- No change to how releases are published or attested; only the interpreter
  used to install, test and build changes.
- No version bump; the release version is chosen when the release is cut.
- No unrelated dependency upgrades. The lock refresh may only remove
  packages needed solely on Python 3.10, move Pillow to 13.0.0 and drop
  `types-Pillow`.

## Artifacts

- Specs: required because the installed package metadata (`Requires-Python`,
  the Pillow requirement) and the `requires-python` of generated projects
  change, and icon generation must keep working on Pillow 13.
- Design: required because this is a toolchain and dependency migration. It
  records what happens to Python 3.10 users, the alternative that was
  rejected, the release-version decision and what each workflow change can
  prove before merge.

## Compatibility and verification

- Python 3.10 users keep working: installers read `Requires-Python` and keep
  them on the last release that supports 3.10. Nothing fails at import time.
- Python 3.11–3.14 users see no API or behavior change.
- Focused proof:
  - packaging tests check that the built wheel's `Requires-Python` excludes
    3.10, that every Python classifier is a version it allows, and that the
    Pillow requirement excludes 12.3.0;
  - the existing entity icon tests and snapshots pass on Pillow 13;
  - a clean-install smoke test scaffolds a project from the built wheel and
    serves its discovery and icons;
  - the SBOM generator runs on Python 3.12.
- Full suite: `poetry run pytest src/tests` on Python 3.12 (the CI
  interpreter) and Python 3.11 (the new floor).
- `openspec validate --all --strict` passes.
