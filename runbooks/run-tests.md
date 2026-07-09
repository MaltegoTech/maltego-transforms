# Runbook: Run tests

The repo uses Poetry and pytest. Async tests run under `pytest-asyncio` with a session-scoped event loop (configured in `pytest.ini`).

## Commands

```bash
poetry install                 # once, if the env is missing
poetry run pytest -q           # full suite
poetry run pytest -m unit -q   # fast subset
poetry run pytest src/tests/unit/test_runner.py -q    # one file
poetry run pytest -m "template or packaging" -q       # combine markers
```

## Markers (scope your run)

| Marker | Covers |
|--------|--------|
| `unit` | Pure model/config/parsing/helpers, no server wiring |
| `integration` | FastAPI apps, server wiring, middleware, async execution |
| `contract` | Stable response status/headers/payload shape |
| `packaging` | Built wheel/sdist, source export, import-smoke |
| `template` | Generated starter/template behavior |
| `security` | Auth, crypto, secret handling, dependency audit |
| `snapshot` | Syrupy snapshots (always pair with explicit assertions) |
| `slow` | Long-running / externally expensive |

## Writing tests

- Look in `src/tests/` for an existing pattern in the matching subdir (`unit/`, `integration/`, `contracts/`, `packaging/`, `templates/`, `security/`) before writing new ones.
- Transform tests are `async def`.
- Pair every snapshot with an explicit behavior/header/status assertion.

## Before claiming done

Run the scoped test suite and confirm it's green — that's the merge gate. `pylint` and `mypy` are configured and worth running, but they are advisory (the codebase is not currently clean under them), so a change isn't blocked on them. Evidence before assertions.
