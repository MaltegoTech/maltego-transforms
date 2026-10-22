## Purpose

The SDK declares and enforces which Python versions it supports, and its
runtime image dependency is a Pillow release without the known advisories,
while entity icon generation keeps producing the same assets.

## ADDED Requirements

### Requirement: Supported Python is 3.11 through 3.14

Built distributions of `maltego-transforms` MUST declare
`Requires-Python: >=3.11,<3.15` and MUST list trove classifiers for Python
3.11, 3.12, 3.13 and 3.14 only. The SDK MUST NOT add a runtime interpreter
check; installers enforce the range through the metadata.

#### Scenario: Wheel metadata declares the range
- **WHEN** the wheel is built and its `METADATA` file is read
- **THEN** `Requires-Python` is `>=3.11,<3.15` and no
  `Programming Language :: Python :: 3.10` classifier is present.

#### Scenario: A Python 3.10 environment does not select this release
- **WHEN** an installer resolves `maltego-transforms` on Python 3.10
- **THEN** it skips releases that declare `>=3.11,<3.15` and selects the
  newest release whose `Requires-Python` includes 3.10.

### Requirement: Generated projects declare the same Python floor

`maltego-transforms start` with `--project-manager poetry` or
`--project-manager uv` MUST write a `pyproject.toml` whose `[project]` table
declares `requires-python = ">=3.11"`. The default `bare` project manager MUST
continue to write no `pyproject.toml`.

#### Scenario: Poetry or uv project
- **WHEN** a project is generated with `--project-manager poetry` or
  `--project-manager uv`
- **THEN** its `pyproject.toml` contains `requires-python = ">=3.11"`.

#### Scenario: Bare project
- **WHEN** a project is generated with the default project manager
- **THEN** no `pyproject.toml` is written.

### Requirement: Runtime Pillow excludes releases before 13.0.0

Built distributions MUST NOT allow Pillow 12.3.0 or older, the releases
affected by the advisories fixed in 13.0.0. Entity icons declared
through `icon_resource` MUST still be generated as PNG images at 16, 24, 32,
48 and 96 pixels and served unchanged from `/api/v3/assets/icons`.

#### Scenario: Wheel metadata excludes vulnerable Pillow
- **WHEN** the wheel's `Requires-Dist` entries are read
- **THEN** the Pillow requirement excludes Pillow 12.3.0.

#### Scenario: Icons are generated with Pillow 13
- **WHEN** a server registers an entity with an `icon_resource` and a client
  requests `/api/v3/assets/icons`
- **THEN** the response contains that icon at every size in
  `ENTITY_ICON_SIZES`, matching the recorded snapshot.
