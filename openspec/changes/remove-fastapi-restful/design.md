## Decision

Remove `fastapi-restful` and own the three helpers the SDK used. Each
replacement reproduces the behavior of the locked `fastapi-restful` 0.6.0
source (`fastapi_restful/api_model.py`, `camelcase.py`, `api_settings.py`,
`tasks.py`) rather than the helper's general-purpose API.

### `APIModel` → `maltego.protocol.api_model.APIModel`

The original class, on Pydantic 2 (the SDK requires `pydantic ^2.13`), is:

```python
model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=partial(snake2camel, start_lower=True),
)
```

with `snake2camel`:

1. `camel = snake.title()`
2. `re.sub("([0-9A-Za-z])_(?=[0-9A-Z])", r"\1", camel)`
3. with `start_lower`, `re.sub("(^_*[A-Z])", lower, camel)`

The new module copies this configuration and a private `_snake2camel` that
keeps those three regex steps verbatim, with MIT attribution to
`fastapi-restful`. The class name stays `APIModel` so every protocol module
changes only its import line. Consequences that are preserved on purpose
because they are on the wire today:

| Field name | Alias | Reason |
| --- | --- | --- |
| `display_name` | `displayName` | plain snake_case |
| `maltego_v3_transform_discovery_message` | `maltegoV3TransformDiscoveryMessage` | `title()` keeps `V3`; underscore before a digit is removed |
| `v2_transform_count` | `v2TransformCount` | leading token with a digit |
| `transformSettings` (`TransformRunRequest`) | `transformsettings` | `title()` lowercases existing capitals; clients send `transformSettings`, accepted via `populate_by_name` |
| `type` / `id` | `type` / `id` | single word |

`pydantic.alias_generators.to_camel` was rejected: it differs on the
`transformSettings` and digit cases, which would change serialized output and
the OpenAPI schema.

### `get_api_settings()` → `maltego.server.fastapi_settings.FastAPIAppSettings`

`get_api_settings()` returned a cached `APISettings(BaseSettings)` with
`env_prefix="api_"` and `validate_assignment=True`; the server cleared the
cache and re-read it on every `MaltegoTransformServer.__init__`, then
overrode `docs_url` and `redoc_url` with `None`.

The replacement is a `pydantic_settings.BaseSettings` subclass (already a
direct SDK dependency) with the same prefix, field names, types, and defaults
for the live fields, and a `fastapi_kwargs` property. The server instantiates
it directly in `__init__`; no cache is needed because the old cache was
cleared before every read.

| `API_*` variable | Effect before | After |
| --- | --- | --- |
| `API_DEBUG` | `FastAPI(debug=...)` | preserved |
| `API_TITLE`, `API_VERSION` | `app.title`/`app.version`; the served OpenAPI document ignores them because `_configure_openapi()` replaces `app.openapi` | preserved |
| `API_OPENAPI_URL` | path of FastAPI's built-in OpenAPI route; `_configure_openapi()` strips only `/openapi.json` | preserved, see Risks |
| `API_OPENAPI_PREFIX` | passed as `openapi_prefix`, which FastAPI maps to `root_path` and logs a deprecation warning for | preserved by passing `openapi_prefix` unchanged |
| `API_DISABLE_DOCS` | sets `openapi_url=None` (and docs/redoc, already `None`) | preserved |
| `API_DOCS_URL`, `API_REDOC_URL` | dead: always overridden with `None` | fields dropped; the result is identical because the server always passes `None` and any string value validated |

Invalid values still raise `pydantic.ValidationError` during server
construction; only the model name in the message changes from `APISettings`
to `FastAPIAppSettings`.

### `repeat_every()` → lifespan-owned `asyncio` task

In 0.6.0, `repeat_every` wraps the loop in a coroutine that is awaited
directly, so `await remove_expired_executions_task()` never returns and the
lifespan never reaches `yield`. The 0.5.x releases scheduled the loop with
`asyncio.ensure_future` instead, which is the intended behavior.

The lifespan now starts `asyncio.create_task()` on a local coroutine that
loops: `await asyncio.sleep(self.scheduled_cleanup_seconds)`, then
`self.runner.cleanup()`, logging with `log.exception(...)` and continuing on
`Exception`. The `yield` is wrapped in `try/finally`; the `finally` block
cancels and awaits the task (suppressing `CancelledError`), then runs the
existing `self.runner.shutdown()` and `await close_validator()`. The rest of
the block is untouched to keep merge conflicts with the parallel
`feat/pluggable-execution-store` branch small.

The first cleanup now happens after one full interval. Under 0.5.x,
`wait_first=True` was passed where a number of seconds was expected, which made
the first call happen after `sleep(True)`, one second. Cleanup of an empty
queue is a no-op, and the runner's `retention_time` equals the interval, so a
later first call removes nothing that would have been retained.

## Migration

- `pyproject.toml`: remove `fastapi-restful = ">=0.5,<0.7"`. `pydantic`,
  `pydantic-settings`, `typing-inspect`, and `fastapi` are already direct
  dependencies. `psutil` becomes unused at runtime; the SDK does not import it,
  so it is not added.
- `poetry lock` must only remove `fastapi-restful` and `psutil`; any other
  version change in the lock diff blocks the change. Relocking the unchanged
  `pyproject.toml` with Poetry 2.5.1 (the lock was written by 2.4.1) already
  produces three non-version differences: the generator header, `protobuf`
  marked `optional = true` for the `tracing` extra (only reachable through
  the OpenTelemetry extras), and a normalized `isort` constraint string in
  `pylint`. These are tool-version artifacts, not caused by this change.
- Generated projects, templates, skills, and requirements files do not
  reference `fastapi-restful`; no template change is required.
- Downstream code that imported `fastapi_restful` directly and relied on the
  SDK to install it must declare it; `CHANGELOG.md` records this.
- Rollback: revert the change; the old lock entry restores 0.6.0, including
  its startup hang.

## Risks and focused verification

- Alias drift would silently change the wire format. Mitigation: a unit test
  pins the tricky aliases against the rules above, existing syrupy snapshots
  must pass unchanged, and captured `/openapi.json`, discovery, and run
  responses from `origin/main` must match byte-for-byte.
- `API_OPENAPI_URL` set to a path other than `/openapi.json` keeps FastAPI's
  unauthenticated OpenAPI route at that path regardless of `swagger_enabled`.
  This pre-existing behavior is preserved to keep the change behavior-neutral;
  closing it belongs in a separate security change.
- Lifespan regression: a unit test enters
  `server.app.router.lifespan_context(server.app)` under
  `asyncio.wait_for(..., 10)` with `scheduled_cleanup_seconds=1` and asserts
  cleanup ran; a real uvicorn start must answer `GET /health` with 200 and
  stop cleanly.
- Full suite: `poetry run pytest -q`; `openspec validate --all --strict`.
