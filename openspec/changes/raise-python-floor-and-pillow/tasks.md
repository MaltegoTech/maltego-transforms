## 1. Establish evidence

- [ ] 1.1 Confirm every Python 3.10 reference in `pyproject.toml`, `src/`, tests, templates, skills, docs and workflows, and the single Pillow call site in `src/maltego/model/__init__.py`.
- [ ] 1.2 Record the baseline: the full suite passes on Python 3.12 with the current lock.
- [ ] 1.3 Make the packaging tests check durable invariants of the built wheel: `Requires-Python` excludes 3.10, every Python classifier is a version it allows, and the Pillow requirement excludes 12.3.0.
- [ ] 1.4 Extend the CLI test so that generated `poetry` and `uv` projects must declare `requires-python = ">=3.11"`.

## 2. Implement: Python floor and workflows

- [ ] 2.1 Set `python = ">=3.11,<3.15"`, remove the 3.10 classifier and refresh the lock; confirm the lock diff only removes 3.10-only packages and markers.
- [ ] 2.2 Write `requires-python = ">=3.11"` in generated `poetry` and `uv` projects.
- [ ] 2.3 Make the `types.UnionType` check in `maltego.util.typing.is_any_union_type` unconditional.
- [ ] 2.4 Update `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, both template READMEs, the shipped skill compatibility notes and `openspec/config.yaml` to Python 3.11–3.14.
- [ ] 2.5 Set `python-version: '3.12'` in `ci.yml`, `prepare-release.yml` and `release.yml`.

## 3. Implement: Pillow 13

- [ ] 3.1 Require Pillow `>=13.0.0,<14`, remove `types-Pillow` and refresh the lock; confirm the diff only moves Pillow to 13.0.0 and drops `types-Pillow`.

## 4. Verify and complete

- [ ] 4.1 Run the focused packaging and CLI tests, then `poetry run pytest src/tests` on Python 3.12 and 3.11 with snapshots unchanged.
- [ ] 4.2 Build the wheel, install it into a clean Python 3.12 environment, generate a project with an entity icon, start it and confirm discovery and `/api/v3/assets/icons` respond.
- [ ] 4.3 Run `resources/generate_sbom.py` on Python 3.12.
- [ ] 4.4 Update `CHANGELOG.md` (Unreleased) and run `openspec validate --all --strict`.
- [ ] 4.5 After the branch is published: confirm pull-request CI passes on 3.12, and dispatch `release.yml` from the branch to confirm its build job passes (its TestPyPI upload job is expected to be rejected off `main`).
