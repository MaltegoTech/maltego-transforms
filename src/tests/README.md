# Test Framework

The test suite is organized into explicit layers. Keep new tests focused and marked so local checks and release checks can select the right risk surface without repeating the same setup across files.

## Layers

| Layer | Marker | Target location | Use for |
| --- | --- | --- | --- |
| Unit | `unit` | `src/tests/unit/` | Entity models, config normalization, helpers, serialization, and pure validation. |
| Server integration | `integration` | `src/tests/integration/server/` | FastAPI apps, middleware, async transform execution, and SDK server wiring. |
| Protocol contracts | `contract` | `src/tests/contracts/v3/` | Stable v3 response status, headers, payload shape, asset metadata, prompt-response behavior, and graph semantics. |
| Packaging | `packaging` | `src/tests/packaging/` | Wheel/sdist contents, clean-environment import smoke tests, source export checks, and generated project smoke tests. |
| Templates | `template` | `src/tests/templates/` | Starter/template generation and scaffold regressions. |
| Security | `security` | `src/tests/security/` | Auth, crypto, credential handling, dependency-audit regressions, and secret-scan fixtures. |

New tests should use the target locations and should always carry the narrowest applicable marker. A test may carry multiple markers when it intentionally crosses layers, for example an integration test that also verifies a protocol contract.

## Current State

All collected tests currently carry at least one taxonomy marker from `unit`, `integration`, `contract`, `packaging`, `template`, or `security`. Long-running or external-fixture tests also carry `slow`, and snapshot-backed tests carry `snapshot` where they have been split out from broader contract coverage.

The physical directory migration is complete for the collected suite. Keep using markers for selection because some tests intentionally live in one directory while covering a second risk surface.

## Fixture Migration

`src/tests/conftest.py` is currently the compatibility surface for a large amount of shared setup. Avoid adding unrelated new fixtures there. Prefer moving cohesive groups into fixture modules and re-exporting only the fixtures needed by existing tests during migration.

| Fixture module | Move from `conftest.py` |
| --- | --- |
| `src/tests/fixtures/entities.py` | Entity classes, typed property examples, rich entity examples, and reusable entity factories. |
| `src/tests/fixtures/oauth.py` | OAuth/JWE token helpers, RSA key helpers, OAuth request builders, and auth-context fixtures. |
| `src/tests/fixtures/server.py` | Server settings, mock servers, middleware test transforms, and async FastAPI clients. |
| `src/tests/fixtures/pagination.py` | Pagination state and paginator fixtures. |
| `src/tests/fixtures/clients.py` | Integration client mock fixtures and client rate-limit helpers. |
| `src/tests/fixtures/runner.py` | Transform result sets, runner fixtures, and execution-context helpers. |
| `src/tests/fixtures/files.py` | Config files, example config files, zip/file helpers, and generated-resource helpers. |

Already extracted fixture modules are re-imported by `conftest.py` so existing tests can keep using the same implicit fixture names during migration. New shared setup should move into a focused fixture module instead of expanding `conftest.py`.

## Assertion Rules

Protocol and integration tests should assert status code, content type, required protocol headers, and the minimum semantic payload before relying on snapshots. Snapshots are useful for broad regressions, but they should not be the only assertion for behavior that clients depend on.

Packaging tests should inspect built artifacts or clean temporary environments instead of importing directly from the source tree. That keeps release checks honest about what public users actually receive.

Security tests should avoid live credentials and should use generated or static test keys only. Any example credential behavior should be asserted as documentation or template behavior, not as a production credential path.

## Snapshot Testing

Snapshot testing is output comparison testing. A first approved result is saved
in a snapshot file, and later test runs compare the current result against that
stored expectation. If the output changes, the test fails so you can decide
whether the change is intentional or a regression.

Snapshots are useful for complex structured outputs such as protocol JSON,
generated files, exported package contents, and transform results. They keep
large outputs consistent across code changes, reduce repetitive manual
assertions, make expected output reviewable in version control, and quickly
surface unintended contract changes.

This test suite uses [Syrupy](https://github.com/syrupy-project/syrupy) through
pytest's `snapshot` fixture. Mark snapshot-backed tests with `snapshot`, keep
explicit assertions for client-critical status codes, headers, fields, and error
semantics, then compare a normalized output to the snapshot:

```python
@pytest.mark.snapshot
async def test_get_assets(async_client, snapshot):
    response = await async_client.get("/api/v3/assets")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert snapshot == normalize_response(response.json())
```

Run snapshot tests normally with pytest. To create or update snapshots after an
intentional output change, run:

```bash
poetry run pytest src/tests --snapshot-update -m snapshot
```

Commit snapshot files together with the test change, and review snapshot diffs
as carefully as code diffs. Normalize unstable values such as generated IDs,
timestamps, binary blobs, and ordering noise before comparing. Name explicit
snapshots when one test checks multiple outputs, and use time-freezing helpers
for time-dependent behavior so snapshots stay deterministic.

## Useful Commands

```bash
poetry run pytest src/tests -m unit
poetry run pytest src/tests -m "contract or integration"
poetry run pytest src/tests -m "packaging or template"
poetry run pytest src/tests -m "security"
poetry run pytest src/tests -m "not slow"
poetry run pytest src/tests --snapshot-update -m snapshot
```
