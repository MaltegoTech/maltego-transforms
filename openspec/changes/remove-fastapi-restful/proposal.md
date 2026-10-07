## Why

`maltego-transforms` depends on `fastapi-restful` for three small helpers:
the `APIModel` base class of every v3 protocol model, `get_api_settings()` for
the `FastAPI(...)` constructor keyword arguments, and `repeat_every()` for the
expired-execution cleanup loop. The locked `fastapi-restful` 0.6.0 changed
`repeat_every()` so that awaiting the decorated function runs the loop inline
and never returns. The server lifespan awaits it before `yield`, so
application startup never completes under uvicorn and the server never
listens. The package also pulls `psutil<6` into every installation although
the SDK does not use it.

Removing the dependency fixes startup and trims the runtime dependency tree,
while the SDK keeps every wire, schema, and configuration behavior it exposed
through `fastapi-restful`.

## Scope and non-goals

In scope:

- Replace `fastapi_restful.api_model.APIModel` with an SDK-owned
  `maltego.protocol.api_model.APIModel` whose Pydantic configuration and alias
  generation match the original exactly.
- Replace `fastapi_restful.api_settings.get_api_settings()` with an SDK-owned
  settings class that reads the same `API_*` environment variables and
  produces the same effective `FastAPI(...)` keyword arguments.
- Replace `repeat_every()` in the server lifespan with an `asyncio` background
  task that is cancelled on shutdown.
- Remove `fastapi-restful` from `pyproject.toml` and relock without bumping
  unrelated packages.
- Record the change in `CHANGELOG.md`.

Non-goals:

- No change to protocol model fields, aliases, serialized payloads, OpenAPI
  output, discovery responses, or snapshots.
- No change to `MaltegoServerSettings`, `scheduled_cleanup_seconds`, runner
  retention, or shutdown ordering beyond the cleanup-task cancellation.
- No refactor of the lifespan block beyond replacing the cleanup scheduler;
  a parallel branch edits the same block.
- No new public configuration surface; the `API_*` variables stay
  undocumented compatibility behavior.

## Artifacts

- Specs: required because server startup under a real ASGI server changes from
  never completing to completing, and the periodic cleanup contract plus the
  preserved protocol alias and `API_*` configuration behavior need to be
  stated as observable requirements.
- Design: required because this is a dependency migration; it records how
  each replaced helper is reproduced, which inherited behavior is dead, and
  how equivalence is proven.

## Compatibility and verification

- Protocol models keep identical `model_config` semantics and aliases; a
  focused unit test pins alias generation for the protocol's tricky field
  names, and existing syrupy snapshots must pass unchanged.
- `/openapi.json` (with `swagger_enabled=True`), v3 discovery responses, and a
  v3 transform run response are captured from `origin/main` and compared
  byte-for-byte after the change.
- `FastAPI` attributes (`debug`, `title`, `version`, `openapi_url`,
  `root_path`, `docs_url`, `redoc_url`) are compared before and after with and
  without `API_*` variables.
- A regression test enters the application lifespan under a timeout and
  asserts cleanup ran; a real uvicorn startup smoke must answer `GET /health`.
- Full `poetry run pytest -q` must pass; `openspec validate --all --strict`
  must pass.
- Downstream projects that imported `fastapi_restful` themselves while relying
  on the SDK to install it must now declare it directly; the changelog states
  this.
