## Decision

Raise the supported floor from Python 3.10 to 3.11, require Pillow 13, and run
the GitHub workflows on Python 3.12.

### Python 3.10 users

The only thing that enforces the floor is the package metadata.
`[tool.poetry.dependencies] python` becomes `>=3.11,<3.15`, so built
distributions carry `Requires-Python: >=3.11,<3.15`. The SDK has no runtime
version guard and gets none. pip, uv and Poetry skip a release whose
`Requires-Python` excludes the running interpreter, so a Python 3.10
environment keeps installing the last 3.10-compatible release. Nothing breaks
for 3.10 users; they stop receiving new releases.

### Release version

The commits are not marked as breaking (no `!` or `BREAKING CHANGE:` footer):
the public API does not change, and installers enforce the floor through the
metadata. On their own, these `docs`/`build`/`ci`/`fix` commits imply only a
patch increment to Commitizen. Commitizen's suggestion is not reliable here
anyway: the release tags are `vX.Y.Z` while `tag_format` is `$version`, so
`cz bump --dry-run` also counts commits from before the last release.
Dropping a supported Python version should ship in at least a minor release,
so the release cutter sets the version explicitly.

The `Unreleased` section of `CHANGELOG.md` is hand-written, like the existing
entries. `cz bump --changelog` would replace it with generated lines, so it is
folded into the release heading by hand.

### Alternative rejected: split the Pillow requirement by Python version

Poetry can express `Pillow = [{version = "^12.3.0", python = "<3.11"},
{version = ">=13.0.0,<14", python = ">=3.11"}]`. That keeps 3.10 installable,
but it pins 3.10 users to a Pillow with a critical heap overflow, on an
interpreter that receives no security fixes either. It also adds a
conditional dependency to maintain. Raising the floor is simpler and fixes
everyone who can be fixed.

### `types-Pillow`

Pillow 13 ships inline type information (`PIL/py.typed`). The
`types-Pillow >=9,<11` development dependency provides stubs for Pillow 10.
Under PEP 561 a stub package takes precedence over inline types, so keeping
it would make `mypy` check the SDK against an outdated API. It is removed.
`mypy` is advisory in this repository, so this affects local analysis only.

### Code that existed only for 3.10

`maltego.util.typing.is_any_union_type` guards the `types.UnionType` check
with `sys.version_info >= (3, 10)`. On 3.11 and newer the guard is always
true, so the branch becomes unconditional, along with the
`pylint: disable=no-member` it needed. No other 3.10-specific code exists in
`src/`. The `sys.version_info >= (3, 14)` branches stay.

## Migration

| Surface | Current | Target |
| --- | --- | --- |
| Package `Requires-Python` | `>=3.10,<3.15` | `>=3.11,<3.15` |
| Classifiers | 3.10–3.14 | 3.11–3.14 |
| Generated `poetry`/`uv` project `requires-python` | `>=3.10` | `>=3.11` |
| Generated `bare` project | no Python pin | unchanged |
| Runtime Pillow requirement | `^12.3.0` (locked 12.3.0) | `>=13.0.0,<14` (locked 13.0.0) |
| CI, Prepare Release, Release build interpreter | 3.11 | 3.12 |
| Poetry used by the workflows | 2.1.4 | unchanged |

Lock refresh: `poetry lock` with Poetry 2.5.1, the version that wrote the
current lock. The diff may only:

- remove packages and markers needed solely on Python 3.10;
- move Pillow from 12.3.0 to 13.0.0;
- drop `types-Pillow`;
- update the metadata `python-versions` and `content-hash`.

Any other version change blocks the change.

Rollback: revert the commits. The previous lock restores Pillow 12.3.0 and the
3.10 floor.

### What each workflow change can prove before merge

| Workflow | Before merge | After merge |
| --- | --- | --- |
| `ci.yml` (`pull_request`, `push`) | Fully: the pull request runs the changed workflow on 3.12 | Runs on every push to `main` |
| `release.yml` build job (`workflow_dispatch`) | Can be dispatched from the branch: install, tests and build on 3.12. The same run also queues the TestPyPI upload job, which the environment rejects, so the run ends as failed even when the build job passes | — |
| `release.yml` TestPyPI upload | Not runnable from a branch: its environment only deploys from `main` or tags. The upload action does not use the job's Python | Dispatch from `main` |
| `prepare-release.yml` | Not runnable by design: it refuses anything but `main` with a draft-release tag on the current commit that matches the package version. Its steps match CI except SBOM generation, which is run locally on 3.12 | First real run when the next release is prepared. Any run needs the version bumped on `main` and a matching draft release, and it attests and attaches assets to that draft |
| `release.yml` PyPI publish | Unaffected: the job does not set up Python | Unchanged |

## Risks and focused verification

- **Pillow 13 changes icon output or behavior.** `add_icon_from_file` uses
  only `Image.open`, `Image.Resampling.BICUBIC`, `resize` and PNG `save`. The
  existing entity icon fixtures, the discovery icon snapshots and the full
  suite must pass unchanged. A clean-install smoke test serves a generated
  project's discovery and icons on 3.12.
- **The lock refresh drifts.** The lock diff is reviewed against the allowed
  list above.
- **3.12 behaves differently from 3.11 in tests.** The full suite runs on both
  3.12 (the workflows) and 3.11 (the floor).
- **The release path breaks on 3.12.** The SBOM generator
  (`resources/generate_sbom.py`) runs locally on 3.12. CI runs the same
  install, test and build steps as both release workflows.
